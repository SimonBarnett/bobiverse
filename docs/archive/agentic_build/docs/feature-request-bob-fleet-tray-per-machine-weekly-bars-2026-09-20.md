<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-bob-fleet-tray-per-machine-weekly-bars-2026-09-20.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: Bob Fleet tray — per-machine weekly bars + IRC peer status (no bogus unreachable)

**Date:** 2026-09-20  
**Repo:** https://github.com/SimonBarnett/agentic_build  
**Raised by:** Simon (via Bob)  
**Evidence:** `docs/screenshots/bob-fleet-tray-single-bar-bogus-unreachable-2026-09-20.png`  
**Build:** Start-BobBuild on **flamingo** (Club Madeira seat)  
**UAT + hostile MRB:** Bob (Simon-raised) — recycle trays on ionos/marchhare/DEV1/flamingo  

## Problem

1. **One bar for the whole fleet is wrong.** Each Bob Fleet machine has its **own** weekly Grok limit (different X Premium seats: ionos Smart Catalogue, flamingo Club Madeira, MarchHare personal, etc.). Four machines ⇒ **four weekly remaining bars**, one under each machine tile (or clearly labeled per id). A single “Weekly remaining −4%” (or any shared %) is incorrect.

2. **Dialog still flaky.** Dark Bob Fleet card sometimes appears, sometimes not (related to click-only tip work / ShowParkedAt). Must be reliable on click; no sticky covering the good tip; no random blank.

3. **“unreachable” is bollocks** when peers are up but filesystem peek fails. Screenshot shows ionos/DEV1/etc. marked unreachable while work continues. If installed-agent peer peek cannot share weekly % / jobs, **use agentic_irc** (Mode 3 / sealed DUMB or cleartext status on the fleet channel) to publish/consume peer weekly remaining + job summaries — do not lie with unreachable.

## Ask

- Per-machine `Get-BobWeeklyRemaining` (or equivalent) painted as a bar on each machine tile.
- Honest status: `ok` / `stale` / `irc-fallback` / `unknown` — reserve `unreachable` for truly dead hosts.
- IRC (or existing agentic_irc moot) as transport when filesystem peer peek cannot see another bridge home.
- Harden card show/hide (click-for-detail; reliable once; no −4% nonsense from bad math/empty source).
- Keep nested jobs under each machine; keep Bob Fleet title.

## Acceptance

1. With N registered machines, card shows **N** weekly bars (or N labeled rows), each from that machine’s billing seat — not one global bar.
2. Click tray icon reliably shows the card; dismiss works; good compact tip not covered (prior FR).
3. No false `unreachable` when IRC (or peek) can supply status; document IRC status schema.
4. UAT screenshots on flamingo + ionos; Test-Pack updates; commit/push; recycle Watch-BobTray on all hosts.

## Out of scope

- Changing weekly quota math at the provider.
- agentic_fomprep / Priority catalog work.
