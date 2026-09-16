# Pitchin 🥗

[![CI](https://github.com/robinaider/pitchin/actions/workflows/ci.yml/badge.svg)](https://github.com/robinaider/pitchin/actions/workflows/ci.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/robinaider/pitchin/badge)](https://scorecard.dev/viewer/?uri=github.com/robinaider/pitchin)

**The free coding agent. Everyone brings a model; nobody pays.**

Freebuff proved coding can be free — funded by ads, served from their gateway, on their terms (peak pauses, session caps, region gates, prompts that personalize ads). Pitchin is the other way to free: **your hardware + free tiers you already own**, routed by [modelwake](https://github.com/robinaider/modelwake), with receipts.

```bash
pip install pitchin modelwake
pitchin agent --config ../modelwake/examples/free.toml --tier FREE \
  --prompt "add a test for the parser and run it" --root ./myproject
pitchin skills
```

- **$0 by construction** — local Ollama → OpenRouter `:free` rows → Gemini free tier; one's 429 is another's turn
- **Strict tool protocol** — one fenced block per turn (`read`/`write`/`edit`/`bash`/`grep`), because small free models follow rigid grammar better than JSON schemas
- **Jailed by default** — everything resolves under `--root`, writes and shell need approval (`--yes` only in scripts you wrote), secrets never go to `:free` rows
- **Skills, not bloat** — `skills/*.md` slash commands (`/plan`, `/review` ship in the box)
- **BYOK escape hatch** — one config line to frontier when free isn't enough; same freedom as connected models, none of the lock-in
- Stdlib only. No gateway, no ads, no accounts, no training on your code.

Ad-funded free wins on zero-config breadth today. Pitchin wins the moment you care who sees your prompts, or a peak-hour pause kills your flow. Different free — pick with eyes open.
