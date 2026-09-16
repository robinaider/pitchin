"""`pitchin serve` — local web UI. Stdlib only (http.server + threads).

Binds 127.0.0.1 by default: this is a coding agent with shell access,
it must never listen on a public interface unless the owner says so
explicitly with --host (and then it is their firewall's problem).
"""

from __future__ import annotations

import itertools
import json
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>pitchin — the free coding agent</title>
<style>
body{background:#0d1117;color:#e6edf3;font-family:system-ui,sans-serif;max-width:860px;margin:2em auto;padding:0 1em}
textarea{width:100%;height:5em;background:#161b22;color:#e6edf3;border:1px solid #30363d;border-radius:8px;padding:.6em}
button{background:#238636;color:#fff;border:0;border-radius:8px;padding:.5em 1.2em;font-size:1em;cursor:pointer;margin:.3em .3em .3em 0}
button.deny{background:#6e3630}button:disabled{opacity:.4}
pre{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:.8em;white-space:pre-wrap;max-height:40vh;overflow:auto}
#appr{display:none;border:1px solid #d29922;border-radius:8px;padding:.8em;margin:1em 0}
small{color:#8b949e}</style></head><body>
<h2>🥗 pitchin <small>free coding agent · local only</small></h2>
<textarea id="p" placeholder="Task, e.g. add a test for the parser and run it"></textarea><br>
<button onclick="start()">Run</button>
<span id="st"><small>idle</small></span>
<div id="appr"><b>Approval needed:</b> <span id="asum"></span><br><br>
<button onclick="decide(true)">Allow</button><button class="deny" onclick="decide(false)">Deny</button></div>
<h3>Final</h3><pre id="fin">—</pre>
<h3>Events</h3><pre id="log">—</pre>
<small id="tlink"></small>
<script>
let id=null,timer=null;
async function start(){
  const r=await fetch("/api/run",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({prompt:document.getElementById("p").value})});
  const j=await r.json(); if(j.error){alert(j.error);return;}
  id=j.id; document.getElementById("st").textContent="running "+id;
  clearInterval(timer); timer=setInterval(poll,1000); poll();
}
async function poll(){
  const r=await fetch("/api/state?id="+id); const s=await r.json();
  document.getElementById("st").textContent=s.status+" · "+s.turns+" turns";
  document.getElementById("log").textContent=s.events.join("\\n")||"—";
  document.getElementById("fin").textContent=s.final||"—";
  const a=document.getElementById("appr");
  if(s.status==="need_approval"&&s.pending){a.style.display="block";
    document.getElementById("asum").textContent=s.pending.tool+": "+s.pending.summary;}
  else a.style.display="none";
  if(s.status==="done"||s.status==="error"){clearInterval(timer);
    document.getElementById("tlink").textContent="transcript: "+s.transcript;}
}
async function decide(allow){
  await fetch("/api/approve",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({id,allow})}); poll();
}
</script></body></html>"""


class ApprovalBridge:
    """Blocks the loop thread until the browser answers (or timeout denies)."""

    def __init__(self, timeout: float = 300.0):
        self._cond = threading.Condition()
        self._pending: dict | None = None
        self._decision: bool | None = None
        self.timeout = timeout

    def ask(self, tool: str, summary: str) -> bool:
        with self._cond:
            self._pending = {"tool": tool, "summary": summary}
            self._cond.notify_all()
            ok = self._cond.wait_for(lambda: self._decision is not None,
                                     timeout=self.timeout)
            decision = self._decision if ok else False
            self._pending, self._decision = None, None
            return bool(decision)

    def decide(self, allow: bool) -> bool:
        with self._cond:
            if self._pending is None:
                return False
            self._decision = bool(allow)
            self._cond.notify_all()
            return True

    def current(self) -> dict | None:
        with self._cond:
            return dict(self._pending) if self._pending else None


class Server:
    def __init__(self, make_backend, root: str = ".", db: str = "pitchin.db",
                 skills: dict | None = None, tier: str = "FREE",
                 timeout: int = 120, max_turns: int = 20,
                 transcript_dir: str = "transcripts",
                 approval_timeout: float = 300.0, max_runs: int = 4):
        self.make_backend = make_backend
        self.root = root
        self.db = db
        self.skills = skills or {}
        self.tier = tier
        self.timeout = timeout
        self.max_turns = max_turns
        self.transcript_dir = transcript_dir
        self.approval_timeout = approval_timeout
        self.max_runs = max_runs
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self.runs: dict[str, dict] = {}

    def start_run(self, prompt: str) -> dict:
        from .loop import run, write_transcript

        with self._lock:
            live = sum(1 for r in self.runs.values()
                       if r["status"] in ("running", "need_approval"))
            if live >= self.max_runs:
                return {"error": f"busy: {live} runs already (max {self.max_runs})"}
            rid = f"run-{next(self._ids)}"
            bridge = ApprovalBridge(timeout=self.approval_timeout)
            state: dict = {"status": "running", "turns": 0, "events": [],
                           "final": "", "reason": "", "transcript": "",
                           "bridge": bridge}
            self.runs[rid] = state

        def events(msg: str) -> None:
            with self._lock:
                state["events"].append(msg)

        def backend(messages):
            with self._lock:
                state["turns"] += 1
                n = state["turns"]
            events(f"turn {n}: asking model…")
            try:
                return self.make_backend(messages)
            except Exception as e:
                events(f"turn {n}: backend error: {e}")
                raise

        def approve(tool, summary):
            events(f"approval: {tool}: {summary}")
            with self._lock:
                state["status"] = "need_approval"
            try:
                ok = bridge.ask(tool, summary)
            finally:
                with self._lock:
                    if state["status"] == "need_approval":
                        state["status"] = "running"
            events(f"approval: {'allowed' if ok else 'denied'}")
            return ok

        def work():
            try:
                res = run(prompt, backend, self.root, approve,
                          max_turns=self.max_turns, skills=self.skills)
                tpath = str(Path(self.transcript_dir) / f"{rid}.jsonl")
                write_transcript(tpath, {"prompt": prompt, "tier": self.tier,
                                         "root": str(self.root),
                                         "via": "serve"}, res.transcript, res)
                with self._lock:
                    state.update(status="done" if res.done else "error",
                                 final=res.final, reason=res.reason,
                                 transcript=tpath)
                events(f"{res.reason} after {res.turns} turn(s)")
            except Exception as e:  # a run must never kill the server
                with self._lock:
                    state.update(status="error", reason=str(e)[:300])
                events(f"error: {e}")

        threading.Thread(target=work, daemon=True).start()
        return {"id": rid}

    def snapshot(self, rid: str) -> dict | None:
        with self._lock:
            st = self.runs.get(rid)
            if not st:
                return None
            return {"status": st["status"], "turns": st["turns"],
                    "events": list(st["events"])[-50:], "final": st["final"],
                    "reason": st["reason"], "transcript": st["transcript"],
                    "pending": st["bridge"].current()}

    def decide(self, rid: str, allow: bool) -> bool:
        with self._lock:
            st = self.runs.get(rid)
            if not st:
                return False
            return st["bridge"].decide(allow)


def make_handler(server: Server):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # keep test output clean
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self):
            try:
                n = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                n = 0
            if not n:
                return {}
            try:
                return json.loads(self.rfile.read(n).decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return {}

        def do_GET(self):
            if self.path == "/" or self.path.startswith("/?"):
                body = PAGE.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            parts = urllib.parse.urlparse(self.path)
            if parts.path == "/api/state":
                rid = urllib.parse.parse_qs(parts.query).get("id", [""])[0]
                snap = server.snapshot(rid)
                if snap is None:
                    self._json({"error": "unknown run"}, 404)
                else:
                    self._json(snap)
                return
            self._json({"error": "not found"}, 404)

        def do_POST(self):
            if self.path == "/api/run":
                data = self._read_json()
                prompt = str(data.get("prompt", "")).strip()
                if not prompt:
                    self._json({"error": "prompt required"}, 400)
                    return
                self._json(server.start_run(prompt))
                return
            if self.path == "/api/approve":
                data = self._read_json()
                ok = server.decide(str(data.get("id", "")),
                                   bool(data.get("allow", False)))
                self._json({"ok": ok})
                return
            self._json({"error": "not found"}, 404)

    return H


def serve_forever(server: Server, host: str = "127.0.0.1", port: int = 8080) -> None:
    httpd = ThreadingHTTPServer((host, port), make_handler(server))
    print(f"pitchin serve on http://{host}:{httpd.server_port} (local only)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
