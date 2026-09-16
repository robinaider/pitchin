"""modelwake backend. Imported lazily so tests never need modelwake installed."""

from __future__ import annotations


def modelwake_backend(config: str, tier: str = "FREE", timeout: int = 120,
                      db: str = "pitchin.db"):
    """Build a Backend callable routing through modelwake's free chains."""
    def go(messages: list[dict]) -> str:
        try:
            from modelwake.config import load as mw_load
            from modelwake.router import auto_tier, route
            from modelwake.transport import openai_chat
        except ImportError as e:
            raise RuntimeError(
                "pitchin needs modelwake: pip install modelwake") from e
        cfg = mw_load(config)
        prompt = _render(messages)
        task = messages[-1].get("content", "") if messages else ""
        use_tier = auto_tier(task) if tier == "auto" else tier
        res = route(cfg, use_tier, prompt, openai_chat,
                    timeout=timeout, db=db)
        return res.text
    return go


def _render(messages: list[dict]) -> str:
    parts = []
    for m in messages:
        role = m.get("role", "user")
        if role == "system":
            continue
        parts.append(f"[{role}]\n{m.get('content', '')}")
    return "\n\n".join(parts)[-12000:]
