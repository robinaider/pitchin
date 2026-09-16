"""Five tools, jailed to root, writes gated by approval. Stdlib only."""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

Approver = Callable[[str, str], bool]  # (tool_name, summary) -> allowed?


class Jail:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def resolve(self, p: str) -> Path:
        target = (self.root / p).resolve()
        if target != self.root and self.root not in target.parents:
            raise PermissionError(f"refused: {p!r} escapes {self.root}")
        return target


def tool_read(jail: Jail, args: dict[str, str]) -> str:
    if "path" not in args:
        return "error: read needs path=\"...\""
    try:
        text = jail.resolve(args["path"]).read_text(encoding="utf-8")
    except FileNotFoundError:
        return f"error: no such file {args['path']!r}"
    except PermissionError as e:
        return f"error: {e}"
    if len(text) > 20000:
        text = text[:20000] + "\n…[truncated at 20k chars]"
    return text


def tool_write(jail: Jail, args: dict[str, str],
               approve: Approver) -> str:
    if "path" not in args or "content" not in args:
        return "error: write needs path=\"...\" content=\"...\""
    if not approve("write", f"write {args['path']}"):
        return "denied: user refused the write"
    try:
        dest = jail.resolve(args["path"])
    except PermissionError as e:
        return f"error: {e}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(args["content"], encoding="utf-8")
    return f"wrote {args['path']} ({len(args['content'])} chars)"


def tool_edit(jail: Jail, args: dict[str, str],
              approve: Approver) -> str:
    if not all(k in args for k in ("path", "old", "new")):
        return "error: edit needs path=\"...\" old=\"...\" new=\"...\""
    if not approve("edit", f"edit {args['path']}"):
        return "denied: user refused the edit"
    try:
        dest = jail.resolve(args["path"])
        text = dest.read_text(encoding="utf-8")
    except FileNotFoundError:
        return f"error: no such file {args['path']!r}"
    except PermissionError as e:
        return f"error: {e}"
    if args["old"] not in text:
        return "error: old string not found (read the file first)"
    if text.count(args["old"]) > 1:
        return "error: old string matches multiple times — be more specific"
    dest.write_text(text.replace(args["old"], args["new"], 1), encoding="utf-8")
    return f"edited {args['path']}"


def tool_bash(jail: Jail, args: dict[str, str],
              approve: Approver) -> str:
    if "cmd" not in args:
        return "error: bash needs cmd=\"...\""
    try:
        timeout = int(args.get("timeout", "30"))
    except ValueError:
        return "error: timeout must be seconds"
    timeout = min(max(timeout, 1), 300)
    if not approve("bash", f"run: {args['cmd'][:120]}"):
        return "denied: user refused the command"
    try:
        p = subprocess.run(["bash", "-c", args["cmd"]], cwd=jail.root,
                           timeout=timeout, capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        return f"error: timed out after {timeout}s"
    except PermissionError as e:
        return f"error: {e}"
    out = (p.stdout + p.stderr)[-4000:]
    return f"exit={p.returncode}\n{out}" if out.strip() else f"exit={p.returncode}"


def tool_grep(jail: Jail, args: dict[str, str]) -> str:
    if "pattern" not in args:
        return "error: grep needs pattern=\"...\""
    base = args.get("path", ".")
    try:
        start = jail.resolve(base)
    except PermissionError as e:
        return f"error: {e}"
    try:
        rx = re.compile(args["pattern"])
    except re.error as e:
        return f"error: bad regex: {e}"
    hits: list[str] = []
    files = [start] if start.is_file() else sorted(start.rglob("*"))
    for f in files:
        if len(hits) >= 30 or not f.is_file() or f.stat().st_size > 200000:
            continue
        if ".git/" in str(f):
            continue
        try:
            for i, line in enumerate(f.read_text(encoding="utf-8",
                                                 errors="replace").splitlines(), 1):
                if rx.search(line):
                    hits.append(f"{f.relative_to(jail.root)}:{i}: {line[:160]}")
                    if len(hits) >= 30:
                        break
        except OSError:
            continue
    return "\n".join(hits) if hits else "(no matches)"


DISPATCH = {
    "read": lambda jail, args, approve: tool_read(jail, args),
    "write": tool_write,
    "edit": tool_edit,
    "bash": tool_bash,
    "grep": lambda jail, args, approve: tool_grep(jail, args),
}


def run_tool(jail: Jail, name: str, args: dict[str, str],
             approve: Approver) -> str:
    fn = DISPATCH.get(name)
    if fn is None:
        return f"error: unknown tool {name!r} (read/write/edit/bash/grep)"
    return fn(jail, args, approve)


def allow_all(tool: str, summary: str) -> bool:
    return True


def deny_all(tool: str, summary: str) -> bool:
    return False


def tty_approver(tool: str, summary: str) -> bool:
    if not os.isatty(0):
        return False
    try:
        ans = input(f"pitchin: allow {summary}? [y/N] ").strip().lower()
    except EOFError:
        return False
    return ans in ("y", "yes")
