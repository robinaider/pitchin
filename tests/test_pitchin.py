"""Hermetic tests. The backend is always scripted — no models, no network."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from pitchin.loop import load_skills, run  # noqa: E402
from pitchin.protocol import parse  # noqa: E402
from pitchin.tools import Jail, allow_all, deny_all, run_tool  # noqa: E402


def scripted(replies):
    it = iter(replies)

    def go(messages):
        try:
            return next(it)
        except StopIteration:
            return "done (script exhausted)"

    return go


class TestProtocol(unittest.TestCase):
    def test_plain_text_is_final(self):
        p = parse("All done, tests pass.")
        self.assertIsNone(p.call)
        self.assertEqual(p.final, "All done, tests pass.")

    def test_fence_parses(self):
        p = parse('thinking\n```tool:read path="a.py"\n```')
        self.assertEqual(p.call.name, "read")
        self.assertEqual(p.call.args, {"path": "a.py"})

    def test_bad_arg_is_error_not_crash(self):
        p = parse('```tool:read nope```')
        self.assertTrue(p.error)

    def test_unknown_tool_surfaced(self):
        with tempfile.TemporaryDirectory() as t:
            out = run_tool(Jail(t), "teleport", {}, allow_all)
            self.assertIn("unknown tool", out)


class TestJail(unittest.TestCase):
    def test_escape_refused(self):
        with tempfile.TemporaryDirectory() as t:
            out = run_tool(Jail(t), "read", {"path": "../../etc/passwd"},
                           allow_all)
            self.assertIn("escapes", out)

    def test_write_denied(self):
        with tempfile.TemporaryDirectory() as t:
            out = run_tool(Jail(t), "write",
                           {"path": "x.txt", "content": "hi"}, deny_all)
            self.assertIn("denied", out)
            self.assertFalse((Path(t) / "x.txt").exists())

    def test_write_allowed(self):
        with tempfile.TemporaryDirectory() as t:
            out = run_tool(Jail(t), "write",
                           {"path": "x.txt", "content": "hi"}, allow_all)
            self.assertIn("wrote", out)
            self.assertEqual((Path(t) / "x.txt").read_text(), "hi")

    def test_edit_exact_match(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "a.py").write_text("x = 1\n")
            out = run_tool(Jail(t), "edit",
                           {"path": "a.py", "old": "x = 1", "new": "x = 2"},
                           allow_all)
            self.assertIn("edited", out)
            out2 = run_tool(Jail(t), "edit",
                            {"path": "a.py", "old": "missing", "new": "z"},
                            allow_all)
            self.assertIn("not found", out2)

    def test_bash_runs_jailed(self):
        with tempfile.TemporaryDirectory() as t:
            out = run_tool(Jail(t), "bash", {"cmd": "pwd"}, allow_all)
            self.assertIn("exit=0", out)
            self.assertIn(str(Path(t).resolve()).split("/")[-1], out)


class TestLoop(unittest.TestCase):
    def test_read_then_edit_then_done(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "v.txt").write_text("version = 1\n")
            replies = [
                '```tool:read path="v.txt"```',
                '```tool:edit path="v.txt" old="version = 1" new="version = 2"```',
                "Bumped to 2.",
            ]
            res = run("bump it", scripted(replies), t, allow_all)
            self.assertTrue(res.done)
            self.assertEqual(res.turns, 3)
            self.assertIn("version = 2", (Path(t) / "v.txt").read_text())

    def test_immediate_answer(self):
        with tempfile.TemporaryDirectory() as t:
            res = run("hi", scripted(["Hello!"]), t, allow_all)
            self.assertTrue(res.done)
            self.assertEqual(res.turns, 1)

    def test_max_turns_stops_runaway(self):
        with tempfile.TemporaryDirectory() as t:
            replies = ['```tool:read path="v.txt"```'] * 50
            (Path(t) / "v.txt").write_text("x\n")
            res = run("loop forever", scripted(replies), t, allow_all,
                      max_turns=5)
            self.assertFalse(res.done)
            self.assertIn("max turns", res.reason)

    def test_backend_error_honest(self):
        with tempfile.TemporaryDirectory() as t:
            def boom(messages):
                raise RuntimeError("HTTP 429: nope")

            res = run("hi", boom, t, allow_all)
            self.assertFalse(res.done)
            self.assertIn("backend error", res.reason)

    def test_skill_invocation_injects_and_continues(self):
        with tempfile.TemporaryDirectory() as t:
            replies = ["/plan", "Planned: nothing to do."]
            res = run("do it", scripted(replies), t, allow_all,
                      skills={"plan": "PLAN BODY"})
            self.assertTrue(res.done)
            self.assertEqual(res.turns, 2)
            texts = [m["content"] for m in res.transcript
                     if m["role"] == "user"]
            self.assertTrue(any("PLAN BODY" in c for c in texts))

    def test_unknown_slash_finishes(self):
        with tempfile.TemporaryDirectory() as t:
            res = run("hi", scripted(["/nope not a skill"]), t, allow_all,
                      skills={"plan": "x"})
            self.assertTrue(res.done)


class TestTranscript(unittest.TestCase):
    def test_jsonl_roundtrip(self):
        import json

        from pitchin.loop import write_transcript
        with tempfile.TemporaryDirectory() as t:
            res = run("bump it", scripted(["fine."]), t, allow_all)
            out = str(Path(t) / "sub" / "run.jsonl")
            write_transcript(out, {"prompt": "bump it"}, res.transcript, res)
            lines = [json.loads(x) for x in Path(out).read_text().splitlines()]
            self.assertEqual(lines[0]["type"], "meta")
            self.assertEqual(lines[0]["prompt"], "bump it")
            self.assertEqual(lines[-1], {"type": "result", "done": True,
                                         "reason": "done", "turns": 1,
                                         "final": "fine."})
            self.assertTrue(any(x["type"] == "message" and x["role"] == "assistant"
                                for x in lines))


class TestSkills(unittest.TestCase):
    def test_loads_md(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "plan.md").write_text("# plan\n")
            self.assertEqual(list(load_skills(str(t))), ["plan"])

    def test_missing_dir_empty(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(load_skills(str(Path(t) / "nope")), {})


class TestServe(unittest.TestCase):
    def test_bridge_allow_deny_timeout(self):
        import threading

        from pitchin.serve import ApprovalBridge
        b = ApprovalBridge(timeout=5.0)
        got = []
        th = threading.Thread(target=lambda: got.append(b.ask("bash", "run x")))
        th.start()
        import time as _t
        for _ in range(100):
            if b.current():
                break
            _t.sleep(0.01)
        self.assertEqual(b.current(), {"tool": "bash", "summary": "run x"})
        self.assertTrue(b.decide(True))
        th.join(timeout=5)
        self.assertEqual(got, [True])

        b2 = ApprovalBridge(timeout=0.05)
        self.assertFalse(b2.ask("write", "f"))  # nobody answers -> deny
        self.assertFalse(b2.decide(True))  # nothing pending

    def test_http_run_end_to_end(self):
        import json as _json
        import threading as _th
        import time as _t
        import urllib.request as _url
        from http.server import ThreadingHTTPServer

        from pitchin.serve import Server, make_handler

        def fake_backend(messages):
            if len([m for m in messages if m["role"] == "assistant"]) >= 1:
                return "All sorted."
            return '```tool:read path="v.txt"```'

        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "v.txt").write_text("v=1\n")
            srv = Server(fake_backend, root=t,
                         transcript_dir=str(Path(t) / "tr"))
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(srv))
            port = httpd.server_address[1]
            _th.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                req = _url.Request(
                    f"http://127.0.0.1:{port}/api/run",
                    data=_json.dumps({"prompt": "read it"}).encode(),
                    headers={"Content-Type": "application/json"})
                rid = _json.loads(_url.urlopen(req, timeout=10).read())["id"]
                final = ""
                for _ in range(100):
                    with _url.urlopen(
                            f"http://127.0.0.1:{port}/api/state?id={rid}",
                            timeout=10) as r:
                        snap = _json.loads(r.read())
                    if snap["status"] in ("done", "error"):
                        final = snap["final"]
                        break
                    _t.sleep(0.05)
                self.assertEqual(final, "All sorted.")
                self.assertTrue((Path(t) / "tr" / f"{rid}.jsonl").exists())
                self.assertTrue(snap["transcript"].endswith(f"{rid}.jsonl"))
            finally:
                httpd.shutdown()

    def test_run_validation(self):
        import json as _json
        import threading as _th
        import urllib.request as _url
        from http.server import ThreadingHTTPServer

        from pitchin.serve import Server, make_handler
        srv = Server(lambda m: "x")
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(srv))
        port = httpd.server_address[1]
        _th.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            req = _url.Request(
                f"http://127.0.0.1:{port}/api/run",
                data=_json.dumps({"prompt": "   "}).encode(),
                headers={"Content-Type": "application/json"})
            try:
                _url.urlopen(req, timeout=10)
                self.fail("expected 400")
            except Exception as e:
                self.assertIn("400", str(e))
        finally:
            httpd.shutdown()


if __name__ == "__main__":
    unittest.main()
