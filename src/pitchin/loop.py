"""The agent loop. Prompt -> one tool -> result -> repeat. Boring on purpose."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .protocol import SYSTEM, Parsed, parse
from .tools import Approver, Jail, run_tool

SKILL_CALL = re.compile(r"/([a-z_][a-z0-9_]*)", re.IGNORECASE)

Message = dict  # {"role": ..., "content": ...}
Backend = Callable[[list[Message]], str]  # messages -> model reply text


@dataclass
class RunResult:
    done: bool
    reason: str
    turns: int
    final: str
    transcript: list[Message] = field(default_factory=list)


def run(task: str, backend: Backend, root: str | Path,
        approve: Approver, max_turns: int = 20,
        skills: dict[str, str] | None = None) -> RunResult:
    jail = Jail(root)
    messages: list[Message] = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": _with_skills(task, skills)},
    ]
    for turn in range(1, max_turns + 1):
        try:
            reply = backend(messages)
        except Exception as e:
            return RunResult(done=False, reason=f"backend error: {e}",
                             turns=turn - 1, final="", transcript=messages)
        messages.append({"role": "assistant", "content": reply})
        parsed = parse(reply)
        if parsed.error:
            messages.append({"role": "user",
                             "content": f"### tool result (protocol): {parsed.error}\n"
                                        "Fix the fence and try again."})
            continue
        if parsed.call is None:
            skill = _invoked_skill(parsed.final, skills or {})
            if skill is not None:
                name, body = skill
                messages.append({"role": "user",
                                 "content": f"### skill /{name}:\n{body}\n"
                                            "Follow it, using tools as needed."})
                continue
            return RunResult(done=True, reason="done", turns=turn,
                             final=parsed.final, transcript=messages)
        out = run_tool(jail, parsed.call.name, parsed.call.args, approve)
        messages.append({"role": "user",
                         "content": f"### tool result ({parsed.call.name}):\n{out}"})
    return RunResult(done=False, reason=f"max turns ({max_turns}) hit",
                     turns=max_turns, final="", transcript=messages)


def _invoked_skill(final: str, skills: dict[str, str]) -> tuple[str, str] | None:
    """A reply starting with /name invokes that skill instead of finishing."""
    m = SKILL_CALL.match(final.strip())
    if not m:
        return None
    name = m.group(1).lower()
    if name in skills:
        return name, skills[name]
    return None


def _with_skills(task: str, skills: dict[str, str] | None) -> str:
    if not skills:
        return task
    names = ", ".join(f"/{n}" for n in sorted(skills))
    return f"{task}\n\nAvailable skills ({names}): say /name to apply one."


def load_skills(d: str | Path) -> dict[str, str]:
    out: dict[str, str] = {}
    base = Path(d)
    if not base.is_dir():
        return out
    for f in sorted(base.glob("*.md")):
        try:
            out[f.stem] = f.read_text(encoding="utf-8")
        except OSError:
            continue
    return out
