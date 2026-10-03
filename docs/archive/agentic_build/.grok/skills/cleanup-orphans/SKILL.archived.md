<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path .grok/skills/cleanup-orphans/SKILL.md, last changed 2026-09-27. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: cleanup-orphans
description: >
  Close orphan python / node / powershell on a fleet Windows box while
  keeping Bob watchers, tray, talk seats, and the live agent session.
  Use when the user says cleanup orphans, close orphan python node
  powershell, prune ghost processes, kill stale irc_listen, duplicate
  Watch-BobJobs, or /cleanup-orphans. Hung named seats are killproc.
  Named Grok Bot hangs are unstick-grok-bot. Skill harvest is
  harvest-agent-skills.
---

# cleanup-orphans

Box hygiene after agent/IRC churn. Not a second NotifyIcon. Not a product
build.

## Keep (never kill)

- This shell's process tree (current Cursor / grok agent).
- Newest one of each: `Watch-BobTray`, `Watch-BobJobs`, `Watch-Bobiverse`,
  `Watch-IrcTsr` / `_Watch-IrcTsr-*`, `Watch-GrokTalk`.
- `bob-<machine>` irc_agent, Jeeves (`--chair`), `bobcallback.py`.
- Current talk-seat listen for `~\.agentic-irc-cursor` (not `cursor2`
  ghosts unless Simon named that seat).
- Newest Xero MCP / intentional MediaHost / VS Code PowerShell hosts.
- `BobFleet-*` scheduled tasks (do not `Stop-ScheduledTask`).
- In-flight `grok.exe` / build workers.

## Kill (orphans)

- Extra `irc_agent` nicks (`ionos-<oldPid>`, duplicate cursor homes).
- Extra `irc_listen` / `Irc-Tsr-Runner` for stale homes (`cursor2`,
  duplicate same-home listeners).
- Duplicate Watch-* (keep newest CreationDate).
- Old `cursor-agent.ps1` + node trees not in this session's keep set.
- Duplicate `npx` / `@xeroapi/xero-mcp-server` pairs (keep newest).
- Bare `powershell.exe` with no `-File` / no useful CommandLine.

## IRC TSR restart loop (PR #334)

If hundreds of orphan `irc_listen` appear every ~30s, check that
`Start-IrcTsr` / `Watch-IrcTsr` / `Watch-CursorIrc` share
`tools/Irc-Tsr-Coordinator.ps1` (bare **or** talk-seat key=value
`coordinator.pid`). Do not `[int]`-parse that file or fall back to the
watcher's `$PID`. After #326 orphans are reaped; after #334 nick drift
no longer respawns every `PollSec`. Sweep orphans here; do not remote
into flamingo from another box unless assigned.

## Command

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\ai\agentic_build\tools\Cleanup-OrphanAgents.ps1
# optional: -WhatIf
```

Prints KEPT / KILLED counts and remaining list. Never prints passwords.

## Related

| Need | Skill / tool |
|------|----------------|
| Kill one hung talk seat + roll | `killproc` / `Stop-HungAgent.ps1` |
| Recycle tray only | `bob-fleet-tray` / `Reinstall-AgentSkills.ps1 -RecycleTray` |
| Start/Restart Bob Systray | `Start-BobFleetTray.ps1` always runs this cleanup + `Clear-BobOrphanNotifyIcons.ps1` |
| Reload skills | `reinstall-agentic-build-skills` |
| Stall / watcher policy | `bob-fleet-monitor` |

## Hard rules

- Do not WinRM other boxes.
- Do not kill every python on the box.
- Do not invent jobs or start product builds.
- After a big orphan sweep, confirm one tray: recycle if zero or >1
  `Watch-BobTray`.
