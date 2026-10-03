<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/bob-irc-agent-supervisor-fr328.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Bob irc_agent supervisor (FR #328)

`tools/Bob-IrcAgentSupervisor.ps1` — pure singleton logic (ensure / cull extras / graceful restart).
`tools/Ensure-BobIrcAgent.ps1` — operator one-shot ensure or `-Restart` (writes `agent.quit.request`, waits, starts).
`tools/Register-BobIrcAgentTask.ps1` — logon + 5-minute keepalive scheduled task (like Jeeves chair).
`Install-BobIrc.ps1` calls ensure (does not force-restart a healthy single agent).

## Operator hotpatch (live box)
```text
powershell -NoProfile -File tools\Ensure-BobIrcAgent.ps1 -MachineId marchhare -Restart
```
Do not run `-Restart` from CI against production without Simon.
