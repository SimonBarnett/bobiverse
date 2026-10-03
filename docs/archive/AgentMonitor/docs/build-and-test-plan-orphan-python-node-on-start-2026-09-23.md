<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/build-and-test-plan-orphan-python-node-on-start-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Plan: orphan cleanup on start
1. Call Stop-OrphanCursorWatchForwards at watch start (after Initialize-WatchIrcHome).
2. Add Stop-OrphanWatchPythonForHome -IrcHome that stops python with that home path in cmdline.
3. Never match forbidden talk-seat homes.
