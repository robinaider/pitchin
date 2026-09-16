"""`pitchin` CLI. Stdlib only. Exit codes: 0 done, 1 stuck/error, 2 usage."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .backend import modelwake_backend
from .loop import load_skills, run
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
    a.add_argument("--yes", action="store_true",
                   help="auto-approve writes/shell (for scripts, not strangers)")

    s = sub.add_parser("skills", help="list available skill files")
    s.add_argument("--skills-dir", default="skills")
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
        print(f"--- {res.reason} after {res.turns} turn(s) ---")
        if res.final:
            print(res.final)
        return 0 if res.done else 1
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
