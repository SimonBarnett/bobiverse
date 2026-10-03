<!-- ARCHIVED COPY - source: SimonBarnett/gh-Jeeves @ 4ff29b5, path docs/feature-request-focus-mutators-fr170-2026-09-26.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR #170: Bob ear may !focus/!unfocus via additive allowlist

## Ask

Simon wants fleet ears (e.g. `bob-ionos`) to run `!focus` / `!unfocus` / `!focus strict` without replacing `JEEVES_OWNER_ACCOUNT`.

## Shape

| Env | Meaning |
|-----|---------|
| `JEEVES_FOCUS_MUTATORS` | Comma-separated **exact** nicks (default empty) |
| `JEEVES_FOCUS_MUTATOR_ACCOUNTS` | Comma-separated services accounts (default empty) |

Both are **additive** to the owner (Simon keeps access). Empty env = today's owner-only behaviour.

When mode_grants is live and a nick-listed mutator has no account (`account=none`), trust is by nick plus the server's nick protection — same model as `!ignore` for `bob-*`. Allowed allowlist commands log `cmd=focus nick=<n> via=allowlist`.

## Acceptance

With `JEEVES_FOCUS_MUTATORS=bob-ionos`, PM `!focus 9 SimonBarnett/agentic_build#369` → `focus: item … rank=9`; `!focus strict on` → `focus strict: on`.

## Tests

`tests/test_focus_mutators_fr170.py`
