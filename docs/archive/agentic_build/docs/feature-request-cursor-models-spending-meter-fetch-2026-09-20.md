<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-cursor-models-spending-meter-fetch-2026-09-20.md, last changed 2026-09-20. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: fetch Spending "Cursor Models" remaining % (not Sand)

**Date:** 2026-09-20
**Repo:** https://github.com/SimonBarnett/agentic_build
**GitHub issue:** https://github.com/SimonBarnett/agentic_build/issues/21
**Raised by:** hostile MRB of `b443f0a70c9bdedfc826e5779de3f36ddac7cb81` (PR #18 / issue #19)
**UAT + hostile MRB owner:** Bob
**Related:** `docs/feature-request-pr-mrb-cursor-models-transaction-2026-09-20.md` (non-goal / follow-up), `box-usage`, `bob-fleet-tray`, `Get-BobCapacity`, `tools/Get-CursorAgentUsage.py`

## Status

**Fetch landed (issue #25):** `Get-CursorAgentUsage.py` reads Spending Cursor Models from `GetCurrentPeriodUsage.planUsage.autoPercentUsed` (percentage points; `1` => 1% used / 99% remaining). `billingCycleEnd` is `period_end` for Cursor Models. Sand stays separate (`sand_used_pct`, `sand_remaining_pct`, `sand_exhausted`, `sand_period_end`) and feeds `Get-BobCapacity` `grok_bot`, not `cursor_models`.

## Gap vs current tree (at b443f0a)

`Get-CursorAgentUsage.py` still calls `GetSandUsageStatus` and writes `remaining_pct` / `used_pct` / `period_end` from **Grok Bot Sand**. `Get-BobCursorAgentWeeklyRemaining` wraps that doc. `Get-BobCapacity` copies it into `cursor_models.remaining_pct`. `Format-BobCursorAccountLabel` still falls through to overage GBP when Sand remaining is null. The tray top bar is labelled `Cursor Models (...)` while the number is Sand remaining or Sand overage.

Live ionos cache `~\.grok\bob-bridge\cursor-agent-usage.json` at MRB time: `used_pct=100`, `remaining_pct=null`, `overage_gbp=55.68`, `period_end=2026-09-23` (Sand reset). Spending on 20 Sep 21:25 showed Cursor Models **1% used** (~99% left), reset **16 Oct**.

`Select-BobGitWorker` treats `cursor_models.remaining_pct > 0` as the fuel gate. With Sand remaining null/0 it can skip Cursor Models while that pool still has headroom — the original #19 problem #4, still red in code. b443f0a docs now tell the truth about which meter is fuel and defer this fetch; they must not be read as "the field already returns Spending Cursor Models".

## Ask

1. Fetch the Spending **Cursor Models** included bar (the dashboard meter that includes Cursor Grok and Composer). Remaining % = 100 − used. Do not invent a number.
2. `Get-BobCapacity.cursor_models.remaining_pct` and the tray top bar must be that remaining %. Period/reset for that row must be the Cursor Models period (20 Sep 2026: reset 16 Oct), not Sand `nextResetTimestampUtc` (23 Sep).
3. Keep Sand as a **separate** signal (`grok-bot` / `Get-BobCursorAgentWeeklyRemaining` or an explicit Sand field). Do not delete overage GBP; show it as overage, never as Cursor Models remaining.
4. Other Models remains unused by this loop and must not be displayed as Cursor Models.
5. Off-DEV Test-Pack: fixture Spending used=1% → remaining 99; Sand 100% / overage present must not become `cursor_models.remaining_pct`.

## LOCKED

- Fuel rule from issue #19: remaining > 0 → Cursor Models (Cursor Grok + Composer); remaining = 0 → grok.exe. Never Other Models.
- Do not scrape a guessed HTML schema. Prefer a documented Cursor API field, or a fixture/manual override until the API is known.
- No `password=` / `XAI_API_KEY=` assignments in git or goals.

## UNKNOWN

- Which `api2.cursor.sh` method (if any) returns the Spending "Cursor Models" included bar versus Sand.
- Whether `GetCurrentPeriodUsage` already contains that bar under a name this tree does not read.

## Acceptance

- `AC1` With a Spending fixture of Cursor Models 1% used, `Get-BobCapacity.cursor_models.remaining_pct` is 99 (not null, not 0, not overage GBP).
- `AC2` Sand 100% used / overage present does not by itself make the fuel gate skip `cursor-models`.
- `AC3` Tray top bar caption is `Cursor Models (N%)` where N is AC1, plus the Cursor Models reset label — not `Cursor Models (-£x.xx)` as the remaining figure.
- `AC4` Test-Pack covers AC1–AC2 off-DEV. No live Cursor cookie scrape in tests.

## Non-goals

- Changing the #19 transaction table (already on b443f0a).
- Auto UAT stamp.
- Using Other Models.

## Implementation note (issue #21 fix)

`GetCurrentPeriodUsage.planUsage.autoPercentUsed` is the Spending **Cursor Models** used %. `billingCycleEnd` is the Cursor Models period end. Sand stays on `GetSandUsageStatus` as `sand_used_pct` / `sand_remaining_pct` / `sand_exhausted`.
