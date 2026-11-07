# FR-OC-FLEET: Per-box OpenCode setup smoke (no secrets)

## Goal

Operators/agents can enable OpenCode on a fleet box using `bob-setup-opencode` with a checklist that never prints keys.

## Deliverables

- Smoke steps: winget/PATH, `opencode --version`, auth.json **presence + ACL** only (never cat body), `opencode run -m <free-or-go> "pong"`, `bob-worker --dry-run` decision.
- Document which machines are OpenCode-enabled (ops note / digest kind) without secrets.
- Tie to FR #6120 trial metrics (optional report template: PRs attempted, first MRB pass, fuel used).

## Testable

1. Checklist script or skill section exits non-zero when opencode missing or dry-run cannot see exe.
2. Skill/docs contain no key material; ACL reset commands only.
3. Failure modes table matches setup skill troubleshoot.
