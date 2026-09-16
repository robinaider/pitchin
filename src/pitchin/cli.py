"""`pitchin` CLI. Stdlib only. Exit codes: 0 done, 1 stuck/error, 2 usage."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .backend import modelwake_backend
from .loop import load_skills, run, write_transcript
from .tools import allow_all, deny_all, tty_approver


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="pitchin",
                                 description="Pitch in — the free coding agent.")
    ap.add_argument("--version", action="store_true")
    sub = ap.add_subparsers(dest="cmd")

    a = sub.add_parser("agent", help="run one task to completion")
    a.add_argument("--config", required=True, help="modelwake TOML (try its free.toml)")
    a.add_argument("--prompt", required=True)
    a.add_argument("--tier", default="FREE")
    a.add_argument("--root", default=".")
    a.add_argument("--db", default="pitchin.db")
    a.add_argument("--timeout", type=int, default=120)
    a.add_argument("--max-turns", type=int, default=20)
    a.add_argument("--skills-dir", default="skills")
    a.add_argument("--transcript", default=None,
                   help="append JSONL transcript (eval dataset) to PATH")
    a.add_argument("--yes", action="store_true",
                   help="auto-approve writes/shell (for scripts, not strangers)")

    s = sub.add_parser("skills", help="list available skill files")
    s.add_argument("--skills-dir", default="skills")

    v = sub.add_parser("serve", help="local web UI (browser chat + approval buttons)")
    v.add_argument("--config", required=True)
    v.add_argument("--tier", default="FREE")
    v.add_argument("--root", default=".")
    v.add_argument("--db", default="pitchin.db")
    v.add_argument("--timeout", type=int, default=120)
    v.add_argument("--max-turns", type=int, default=20)
    v.add_argument("--skills-dir", default="skills")
    v.add_argument("--transcript-dir", default="transcripts")
    v.add_argument("--port", type=int, default=8080)
    v.add_argument("--host", default="127.0.0.1",
                   help="bind address (default localhost only — see serve.py)")
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    if getattr(args, "version", False):
        print(f"pitchin {__version__}")
        return 0
    if args.cmd == "skills":
        skills = load_skills(args.skills_dir)
        if not skills:
            print(f"no skills in {args.skills_dir}/ (add *.md files)")
            return 0
        for name in sorted(skills):
            first = skills[name].strip().splitlines()[0][:80]
            print(f"/{name}: {first}")
        return 0
    if args.cmd == "agent":
        approve = allow_all if args.yes else tty_approver
        try:
            backend = modelwake_backend(args.config, tier=args.tier,
                                        timeout=args.timeout, db=args.db)
            skills = load_skills(args.skills_dir)
        except Exception as ex:
            print(f"pitchin: {ex}", file=sys.stderr)
            return 2
        res = run(args.prompt, backend, args.root, approve,
                  max_turns=args.max_turns, skills=skills)
        if args.transcript:
            write_transcript(args.transcript,
                             {"prompt": args.prompt, "tier": args.tier,
                              "root": str(args.root),
                              "max_turns": args.max_turns},
                             res.transcript, res)
        print(f"--- {res.reason} after {res.turns} turn(s) ---")
        if res.final:
            print(res.final)
        return 0 if res.done else 1
    if args.cmd == "serve":
        from .serve import Server, serve_forever
        skills = load_skills(args.skills_dir)

        def make_backend(messages):
            from modelwake.config import load as mw_load
            from modelwake.router import route
            from modelwake.transport import openai_chat
            cfg = mw_load(args.config)
            from .backend import _render
            res = route(cfg, args.tier, _render(messages), openai_chat,
                        timeout=args.timeout, db=args.db)
            return res.text

        if args.host not in ("127.0.0.1", "localhost", "::1"):
            print("pitchin: WARNING: binding a non-local address exposes a "
                  "shell-capable agent to the network. Your call.", file=sys.stderr)
        serve_forever(Server(make_backend, root=args.root, db=args.db,
                             skills=skills, tier=args.tier,
                             timeout=args.timeout, max_turns=args.max_turns,
                             transcript_dir=args.transcript_dir),
                      host=args.host, port=args.port)
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
