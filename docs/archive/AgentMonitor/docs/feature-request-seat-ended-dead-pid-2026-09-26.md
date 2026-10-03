<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/feature-request-seat-ended-dead-pid-2026-09-26.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: seat ended when nick/seat PID dead

See https://github.com/SimonBarnett/AgentMonitor/issues/136

Ensure writes live seat= before irc_agent start; re-nicks when suffix PID is dead; prefers TUI rootPid.
