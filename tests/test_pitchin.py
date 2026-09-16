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


class TestSkills(unittest.TestCase):
    def test_loads_md(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "plan.md").write_text("# plan\n")
            self.assertEqual(list(load_skills(str(t))), ["plan"])

    def test_missing_dir_empty(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(load_skills(str(Path(t) / "nope")), {})


if __name__ == "__main__":
    unittest.main()
