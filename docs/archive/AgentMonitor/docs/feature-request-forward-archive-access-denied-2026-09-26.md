<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/feature-request-forward-archive-access-denied-2026-09-26.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: IRC forward must survive locked oversized session archive

**Date:** 2026-09-26  
**Repo:** SimonBarnett/AgentMonitor  
**Symptom (marchhare):** `Watch-AgentHealth` logged `irc-in` assigns from Jeeves, then `forward failed: Access to the path '…\sessions\C%3A%5Cai\<sid>' is denied` and never woke the TUI.

## Cause
FR #99 oversized rotate calls `Move-Item` on the live Grok session folder. The visible TUI keeps `updates.jsonl` locked. `Move-Item` throws; `Send-IrcLineToSession`'s catch drops the wake.

## Acceptance
1. Locked/oversized session: archive reports failure without throwing.
2. Monitor still mints a new `sessionId` and forwards `-p` (IRC assign reaches the seat).
3. Successful archive path unchanged (move, never delete).
4. Test `AM99e` covers exclusive lock → soft fail → new session id.

## Non-goals
Do not delete session folders. Do not reimplement IRC in the agent.
