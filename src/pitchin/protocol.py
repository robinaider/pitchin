"""Strict text tool protocol. Weak free models follow rigid grammar far
better than nested JSON schemas: exactly one fenced block per turn.

    ```tool:read path="src/x.py"
    ```

No fence in a reply means the agent is done talking and the text is final.
A fence that fails to parse becomes a tool *error result*, never a crash —
the model gets to correct itself next turn.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

FENCE = re.compile(r"```tool:([a-z_]+)(.*?)```", re.DOTALL)


@dataclass
class ToolCall:
    name: str
    args: dict[str, str]


@dataclass
class Parsed:
    call: ToolCall | None
    final: str
    error: str = ""


def parse(reply: str) -> Parsed:
    m = FENCE.search(reply)
    if not m:
        return Parsed(call=None, final=reply.strip())
    name, raw = m.group(1), m.group(2).strip()
    try:
        parts = shlex.split(raw)
    except ValueError as e:
        return Parsed(call=None, final="", error=f"bad tool args: {e}")
    args: dict[str, str] = {}
    for p in parts:
        if "=" not in p:
            return Parsed(call=None, final="",
                          error=f"bad tool arg {p!r}: want key=\"value\"")
        k, v = p.split("=", 1)
        args[k] = v
    return Parsed(call=ToolCall(name=name, args=args), final="")


SYSTEM = """You are pitchin, a free coding agent. You have five tools, one per turn:

```tool:read path="..."```
```tool:write path="..." content="..."```
```tool:edit path="..." old="..." new="..."```
```tool:bash cmd="..." timeout="30"```
```tool:grep pattern="..." path="..."```

Rules: exactly ONE fenced tool block per reply, args as key="value".
Read before you edit. Smallest change that fixes the task.
Reply with plain text (no fence) only when the task is fully done.
Never print secrets. Never touch paths outside the project.
"""
