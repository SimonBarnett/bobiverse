<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/feature-request-monitor-adopt-live-agent-2026-09-25.md, last changed 2026-09-25. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: monitor restart adopts live agent + stable nick (AgentMonitor #89)

## Reload path (do not duplicate TUI)

1. Leave the live `agent.exe` / Composer TUI running.
2. Stop **only** the old `Watch-AgentHealth` monitor process (not the seat TUI).
3. Start a new monitor with the same kind/home, preferably `-Reload`:

```text
powershell -NoProfile -ExecutionPolicy Bypass -File Watch-AgentHealth.ps1 -Grok -WatchWorker -Reload
```

On start the monitor logs `watch reload FR#89 build=adopt-live-agent` (or `watch build FR#89-adopt-live-agent`).
If `state.rootPid` is alive and its command line contains `state.sessionId`, it **adopts** that tree and does **not** call `Start-WatchedAgent`.
`Ensure-WatchIrcSeat` keeps `ircNick` / `seatNickPid` when irc_agent is already up (no second listen/agent for the same home).

## Live check (operator)

Reload monitor on a live seat; confirm agent.exe PID and IRC nick unchanged; new log line shows FR#89 build. Do not restart the live Desktop monitor from CI/agents without Simon.
