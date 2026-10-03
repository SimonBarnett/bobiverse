<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-digest-cursor-pools-period-end-2026-09-28.md, last changed 2026-09-28. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: digest reports per-pool Cursor resets (Sand weekly vs billing)

**Date:** 2026-09-28
**Repo:** https://github.com/SimonBarnett/agentic_build
**GitHub issue:** https://github.com/SimonBarnett/agentic_build/issues/456
**Sister:** https://github.com/SimonBarnett/gh-Jeeves (persist `machines.*.cursor_pools` + `sand_period_end`)
**Surface:** `Write-BobIrcStatus`, `Build-BobDigestWebhookMergePayload`, TipForm / `bob-digest-webhook`
**Raised by:** Simon (TipForm screenshot + Cursor Spending dashboard — grok chat weekly vs Auto/API billing)

## Problem

Cursor Spending has three distinct pools:

| TipForm bar | Source | Reset |
|---|---|---|
| grok chat | Sand / Grok chat | weekly (`sand_period_end`) |
| high cost models | API | billing cycle (`cursor_period_end`) |
| low cost models / auto | Auto + Composer | billing cycle |

Local TipForm paint already separates them (FR #448). The digest **merge** dropped `cursor_pools` and never sent `sand_period_end`, so fleet GET had `cursor_pools: []` and peers could not learn the correct clocks.

## Ask

1. Every Bob POSTs slim `cursor_pools` with per-group `remaining_pct` + `period_end`.
2. POST `sand_period_end` beside `cursor_period_end`.
3. Fingerprint / chair-in-sync include those fields.
4. gh-Jeeves persists `machines.<id>.cursor_pools` + `sand_period_end` (top-level `cursor_pools` already accepted).

## Acceptance

- Digest GET after heartbeat: non-empty `cursor_pools`; grok-chat `period_end` = Sand weekly; high/auto = billing.
- Hermetic BT0 #456 PASS.
- TipForm: grok chat countdown differs from high/auto when Sand and billing differ.
