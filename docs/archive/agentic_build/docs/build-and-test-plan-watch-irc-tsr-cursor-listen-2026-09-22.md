<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/build-and-test-plan-watch-irc-tsr-cursor-listen-2026-09-22.md, last changed 2026-09-25. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: IRC TSR + Cursor listen watchdog (issue #163)

**Date:** 2026-09-22  
**Repo:** https://github.com/SimonBarnett/agentic_build  
**Issue:** https://github.com/SimonBarnett/agentic_build/issues/163  
**Spec:** `docs/feature-request-watch-irc-tsr-cursor-listen-2026-09-22.md`  
**Chair:** Bob (hostile MRB on #163). Builder opens PR; never push `main`; never merge.

## Goals

- `Start-IrcTsr.ps1` / `Irc-Tsr-Runner.ps1` run `irc_listen.py`, append `PROCESS_HEARTBEAT` to `irc-tsr-*-wake.jsonl` on start and every 30s while listen is alive, and emit `AGENT_LOOP_WAKE_irc-tsr` on `FROM` lines.
- `Watch-IrcTsr.ps1` restarts TSR when runner/listen child is gone, runner age exceeds cap, or **process** wake heartbeat is stale.
- Idle `#bobiverse` must not recycle: silence gate uses last `PROCESS_HEARTBEAT` in the wake jsonl (not `irc.log` or `FROM` mtime; missing wake is not stale until heartbeat is written).
- `Watch-CursorIrc.ps1` keeps `cursor-<machine-id>` `irc_agent` + TSR up; `Watch-Bobiverse.ps1` stays dumb.
- `Install-BobFleet` registers `_Watch-IrcTsr-<id>` and `_Watch-CursorIrc-<id>` (AtLogOn + demand start).
- Off-DEV Test-Pack only; no live Ergo; no secret assignments in git.

## Implementation

1. Add `tools/Irc-Tsr-Health.ps1` (wake stale + runner core matrix for tests).
2. Add TSR runner/start/watch scripts and `_Watch-*` wrappers (per-machine ionos copies set `BOB_MACHINE_ID`).
3. Extend `tools/Install-BobFleet.ps1` for IRC TSR and Cursor IRC scheduled tasks.
4. Test-Pack `BT0irtsr*` cases for wake matrix, install wiring, and Watch-Bobiverse isolation.
5. **PR #334 (flamingo 24–25/09):** shared `tools/Irc-Tsr-Coordinator.ps1` so `Start-IrcTsr` / `Watch-IrcTsr` / `Watch-CursorIrc` agree on `irc-tsr-<nick>.pid`.
   - `coordinator.pid` is **two formats**: bare PID **or** talk-seat key=value (`nick=` / `agent=` / `seat=`). Never `[int](Get-Content -Raw)` and never fall back to the caller's `$PID` (that nick drift restarted TSR every `PollSec` → 1833 orphaned `irc_listen` on flamingo before #326 orphan reap).
   - `Get-IrcTsrCoordinatorNick` → `<machine>-<id>` or `<machine>-coord` when unknown.
   - `Initialize-IrcTsrCoordinatorPid` writes a bare id only when the file is **missing** (never overwrites a seat file).
   - `Get-IrcTsrRestartDelaySec` exponential respawn backoff (base×2^n, cap 600s) when restarts never turn healthy; healthy tick resets.
   - `Watch-IrcTsr` re-resolves nick each tick (`Update-TsrWatchPaths`).

## Tests (off-DEV)

| ID | Case | Acceptance |
|---|---|---|
| BT0irtsr1 | wake silence matrix | AC2/AC3 healthy vs stale wake; idle irc.log does not affect wake-only gate |
| BT0irtsr2 | runner core matrix | AC2 dead runner / missing listen / age cap |
| BT0irtsr3 | install + bobiverse | AC1 wiring; Watch-Bobiverse unchanged |
| BT0irtsr-coordinator-nick | coordinator.pid nick + backoff (PR #334) | flamingo key=value fixture; old `[int]` throws; shared parser; no `$PID` fallback; backoff series; static wiring on Start/Watch scripts |

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\ai\agentic_build\tools\Test-Pack.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File C:\ai\agentic_build\tests\BT0irtsr-coordinator-nick.ps1
```
