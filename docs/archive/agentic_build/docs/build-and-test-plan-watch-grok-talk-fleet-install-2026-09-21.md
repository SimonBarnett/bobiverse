<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/build-and-test-plan-watch-grok-talk-fleet-install-2026-09-21.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: Install Watch-GrokTalk on fleet boxes (issue #128)

**Date:** 2026-09-21  
**Repo:** https://github.com/SimonBarnett/agentic_build  
**Issue:** https://github.com/SimonBarnett/agentic_build/issues/128  
**Spec:** `docs/feature-request-watch-grok-talk-fleet-install-2026-09-21.md`  
**Chair:** Bob (hostile MRB on #128). Builder opens PR; never push `main`; never merge.

## Goals

- `Install-BobFleet` registers per-machine `_Watch-GrokTalk-<id>` (AtLogOn + demand start) for the grok-talk poller.
- `Watch-Bobiverse.ps1` stays dumb (no `Invoke-BobGrokTalkTick`, no grok-inbox, no grok.exe start).
- Off-DEV Test-Pack only; no live Ergo; no secret assignments in git.

## Implementation

1. Add `tools/_Watch-GrokTalk.ps1` thin wrapper → `Watch-GrokTalk.ps1` (same pattern as `_Watch-Bobiverse.ps1`).
2. Extend `tools/Install-BobFleet.ps1`: register/start `_Watch-GrokTalk-<machineId>`; skip duplicate start if poller already running.
3. Test-Pack: assert install wiring and wrapper delegation (BT0 tray block + BT0gtalk block).

## Tests (off-DEV)

| ID | Case | Acceptance |
|---|---|---|
| BT0n | tray / install surface | AC1 install registers `_Watch-GrokTalk-<id>`; wrapper exists |
| BT0gtalk | grok-talk inbox worker | AC2 Watch-Bobiverse unchanged; AC3 install task registration |

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\ai\agentic_build\tools\Test-Pack.ps1
```
