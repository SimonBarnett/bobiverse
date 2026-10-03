<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/monitor-reload-fr89.md, last changed 2026-09-25. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Monitor reload (FR #89)

Safe hotpatch of `Watch-AgentHealth.ps1` without duplicating the agent TUI or renaming the seat.

## Behaviour
- **Adopt live agent:** if `state.rootPid` is alive and its command line contains `sessionId`, the monitor sets `$current` to that tree and does **not** call `Start-WatchedAgent` (no second TUI).
- **Stable nick:** `Resolve-StableWatchIrcNick` keeps `state.ircNick` / live `irc_agent --nick` across monitor PID changes.
- **Dead rootPid:** still restarts the agent (existing health loop).

## Operator steps
1. Deploy the new script to the install path (e.g. Desktop `Watch-AgentHealth`).
2. Stop **only** the monitor PowerShell process (not `agent.exe` / `irc_agent` / `irc_listen`).
3. Start the worker with the same flags **plus `-Reload`**, for example:

```text
powershell -NoProfile -ExecutionPolicy Bypass -File Watch-AgentHealth.ps1 -WatchWorker -Grok -Windows off -Reload
```

4. Confirm log contains `watch reload FR#89 build=adopt-live-agent` and an adopt line with the **same** `rootPid` / nick.

Do **not** pass `-New` for a hotpatch (that resets the session).
