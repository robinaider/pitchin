# Security policy

Pitchin is a coding agent: it reads/writes files and runs shell commands
**only** inside the `--root` jail and **only** with your approval
(`--yes` auto-approves — use it solely in scripts you wrote yourself).
`pitchin serve` binds localhost only. Prompts go to the configured model
backend; never send secrets to `:free` rows or endpoints whose data-use
terms you haven't read.

## Reporting a vulnerability

**Please do not open a public issue for security reports.** Disclose privately via
https://github.com/robinaider/pitchin/security/advisories/new
so we can fix before details go public.

Please include a minimal repro and the version (`pitchin --version`).
We aim to acknowledge within 72 hours and share a fix plan within 14 days,
and will credit reporters in `CHANGELOG.md` unless you ask otherwise.
We follow coordinated vulnerability disclosure: please allow up to 90 days
before public disclosure of the vulnerability.

## Supported versions

| Version | Supported |
|---|---|
| Latest PyPI release (`pip install -U pitchin`) | ✅ |
| Older releases | ⚠️ best-effort — please upgrade, re-test, and re-report |

## Scope notes

- The jail refuses any path resolving outside `--root`.
- Approval timeouts deny. Denied actions are reported, never retried silently.
