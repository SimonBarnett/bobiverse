<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/feature-request-irc-health-log-and-agent-field-2026-09-26.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: IRC PART seat ended from stale coordinator agent=

**Root cause:** `talk_seat_pid.coordinator_seat_pid` prefers `agent=` over `seat=`.
Watch-AgentHealth wrote `agent=<irc_agent pid>`. On restart, a new irc_agent read a
**dead** `agent=` and PART'd `seat ended` while the TUI (`seat=`) was still alive.

**Fix:** `Write-WatchCoordinatorPid` sets `agent=$SeatPid` (live TUI/host) and stores
the python pid in `irc_agent=`. `Write-WatchIrcHealthSnapshot` logs health ticks /
disconnect / ensure for diagnosis.

**Logging:** `irc-health tag=...` lines in Watch-AgentHealth.log.
