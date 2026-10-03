<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path .grok/skills/bob-fleet-monitor/SKILL.md, last changed 2026-09-19. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: bob-fleet-monitor
description: >
  This grok.exe session is the IONOS stall monitor only. Watch Watch-BobAgents /
  the tray; heal the pull worker; do not dispatch or kill Bob's product jobs.
  Use when the user says you are the monitor, let Bob run them, stall monitor,
  ACTION_REQUIRED, watcher_down, inbox_stale, running_orphan, or
  /bob-fleet-monitor. Tray UI is bob-fleet-tray. Named-bot hangs are
  unstick-grok-bot. Job queue dispatch is grok-build-fleet / bob-build-dispatch.
---

# Fleet monitor (this session)

You monitor. **Bob** (Grok Bot) starts product jobs. Do not `Start-BobBuild` for his work. Do not `Stop-BobBuild` unless the user asks. Do not `Stop-ScheduledTask BobFleet-*` while `Get-BobBuilds -Lane running` has a live `grok.exe`.

## Watch

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$repo\tools\Watch-BobAgents.ps1"
```

Human UI: `bob-fleet-tray`. Stdout ACTION_REQUIRED only.

| Token | Do |
|---|---|
| `watcher_down` | If a running job has live grok.exe, leave it. If idle (`running=0`, no matching grok.exe), `Start-ScheduledTask BobFleet-<id>` only. Never stop the task to "heal" a busy watcher. |
| `inbox_stale` | Queue behind a live running job is not stale. Idle watcher + sitting inbox: start the task if it is not running. Do not steal the job. |
| `running_orphan` | Report. Do **not** `Stop-BobBuild`. Bob requeues. |
| `agent_stall <name>` | `unstick-grok-bot` for that name. Do not start a fleet build in its place. |

`lastSeen` is tick-start (and Complete-FleetJob). A long grok.exe hold is healthy.

## Hard rules

- No WinRM. No Windows service.
- No `--yolo` on formprep.
- No SQL passwords / `XAI_API_KEY=` / `password=` assignments in packets.
