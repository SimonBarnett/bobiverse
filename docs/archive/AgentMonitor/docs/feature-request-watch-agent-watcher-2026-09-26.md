<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/feature-request-watch-agent-watcher-2026-09-26.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: Watch-AgentWatcher (meta-monitor for Watch-AgentHealth)

**Date:** 2026-09-26

## Why
Watch-AgentHealth (the agent watcher) repeatedly died or left IRC with
`PART … seat ended` while the TUI stayed up. Operators saw "lost IRC" without
a clear line in the log tying cause → effect.

## Findings (hotfixed + logged)

| Finding | Fix |
|---------|-----|
| `talk_seat_pid` prefers `agent=` over `seat=`; writing `agent=<irc_agent pid>` made restarts PART | `Write-WatchCoordinatorPid`: `agent=$SeatPid` (TUI), python in `irc_agent=` |
| `$Home` param is read-only in PS 5.1 | Rename to `-SeatHome` |
| Unicode emdash broke parse | ASCII-only log strings |
| Grok `Responding=$false` false unhealthy | Root-PID-only `Test-TreeHealthy` |
| Monitor exit tore down IRC while TUI alive | `finally` leaves IRC up |

## Tool
`tools/Watch-AgentWatcher.ps1`

- Checks: WatchWorker process, irc_agent/listen, seat alive, `agent==seat`, log errors, irc.log PART
- Writes `Watch-AgentWatcher.log` next to the watch log
- Optional `-Heal` relaunches `Watch-AgentHealth -Reload`
- `-Once` for tests / one-shot; default loop every 30s

## Logging in Watch-AgentHealth
`irc-health tag=…` snapshots on ensure / missing / tick / disconnect.

## Finding: sticky seatRootGone death loop (2026-09-26)
Heal/`-Reload` left `state.seatRootGone=true` and `rootPid=0` (session id also
drifted). Monitor: Ensure IRC → `seat root gone - monitor exit` → prune orphan
python → IRC gone. Meta-watcher saw FAIL and Heal-looped.

**Fix:** On `-Reload`, if a live `agent.exe` still hosts `state.sessionId` (or
adopt succeeds), clear `seatRootGone` and restore `rootPid`.

## Finding: prune on Reload kills live IRC (!bored correlation)
`Stop-OrphanWatchPythonForHome` ran at monitor start with `ExcludePid=$PID`, saw
**no sibling worker**, and killed live `irc_agent`/`irc_listen`. Heal/`!bored`
activity restarts the monitor → prune → disconnect → Ensure JOIN storm.

**Fix:** If coordinator `seat=` is a live TUI and IRC procs are up, skip prune.
