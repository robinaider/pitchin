# Changelog

## [Unreleased]
- `pitchin serve`: local web UI (stdlib ThreadingHTTPServer, localhost-only) with browser chat, approval Allow/Deny buttons, live events, per-run JSONL transcripts.
- `--transcript PATH`: append JSONL transcripts (the future eval dataset) on CLI runs.
- Fix: `/skill` replies now inject skill content instead of ending the run (advertised skills were dead on arrival).

## [0.1.0] - 2026-09-16
- Initial release: strict text tool protocol, 5 jailed tools, approval gating, modelwake backend, markdown skills, 15 hermetic tests.
