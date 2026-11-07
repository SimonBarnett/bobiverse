# Functional spec - digest ear-publish + TipForm fuel logos

Pulled from LOCKED vision (plan-20261107-132147).

## Publish

- ircBob ear builds merge payload: weekly, period_end, pcent (incl. opencode-free/opencode-go when known), cursor_pools, xAI account label, Copilot pool refresh contribution as applicable.
- POST op=merge to https://bob.ntsa.uk/bob/v1/report (config reportUrl / helpers).
- On any remaining/reset/account/OpenCode/Copilot delta: POST immediately (fingerprint must include those fields).
- Watch-BobTray / TipForm must not POST fuel merges (GET/paint only).

## Consume / paint

- TipForm and Status show four families with logos: Cursor, xAI/Grok, OpenCode, Copilot.
- Unknown = n/a (omit or null; never invent 0 for unknown).
- Copilot line must not present multi-day-stale fetched_at as current without a stale marker.
- Local Cursor Spending remains Agents start fuel-gate when known.

## Fields

- machines.<id>.pcent.opencode-free / opencode-go (int remaining % or omit)
- machines.<id> xAI account label field (name pinned in FR-003; not bob-<machine> alone)
- report.copilot with fresh fetched_at when refresh succeeds

## Tests

- Ear posts; tray does not
- URL default bob.ntsa.uk
- OpenCode pcent round-trip (extends test_opencode_digest_6120)
- Lag fixture: remaining change -> GET within bound
- TipForm/Status paint pins for logos + OpenCode + Copilot