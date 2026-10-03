<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path .grok/skills/agent-monitor/SKILL.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: agent-monitor
description: >
  AgentMonitor / Watch-AgentHealth desktop watch seat. Starts Grok or Cursor,
  tails irc.log, forwards FROM into the session. Use when launching the
  watcher, Cursor New/Resume, no TUI, prune leftover cursor-agent nodes,
  print-only, -Windows off, or explaining what the monitor does.
---

# AgentMonitor

Deterministic **watch-seat** monitor (`Watch-AgentHealth.ps1`). It is not a
talk seat. The TUI agent gets IRC only via monitor-forwarded `FROM` lines
(skill `watch-seat`).

## Split

| Who | Owns |
|-----|------|
| Monitor | Start TUI, persist session, health, **Ensure-WatchIrcSeat** (`irc_agent` + `irc_listen` on the watch home, JOIN own `#{machine}` ONLY, never `#bobiverse` / `#agentic_irc`), tail `irc.log`, forward each PRIVMSG as `FROM`, **emit `!bored`** on start / after DONE / while idle (FR #100; no LLM). **`-SeatType loop` / `-NoBored`** (FR #103) suppress every `!bored` and use `-Channel`/`-Nick` for continuous non-job agents |
| Agent | Act on forwarded `FROM`, **append** `outbox.txt` (never overwrite). Fleet ACK/DONE: line starts with `ACK`/`DONE` (no nick prefix); DONE ends at URL (FR #104 / `watch-seat`). Never post `!bored` yourself (loop seats never ACK/DONE to Jeeves) |

The agent does not run, restart, or reimplement the monitor. CAST IRON
(Simon 2026-09-23): **systray Agents / Watch-AgentHealth launch MUST connect
IRC** (ensure after orphan prune). If agent or listen dies while the seat is
live, the monitor re-ensures. On TUI exit the monitor writes `quit.req` so
`irc_agent` PARTs every watch channel then QUITs.

**CAST IRON — PING:** the watcher **always** auto-pongs seat-directed
`ping`/`PING` (bare or addressed to this nick) on `outbox.txt` and **never**
forwards that line to the agent. Busy seats still answer so the fleet knows
they are responding.

## Launch

Visible by default (watch console + agent TUI). There is **no `on` flag**.

```bat
Watch-AgentHealth.cmd cursor
Watch-AgentHealth.cmd cursor new
Watch-AgentHealth.cmd grok
Watch-AgentHealth.cmd grok off
```

- **Default / `new`** — fresh session id + skills + prompt. Tray Agents always
  `-New` and Cursor `-Model auto`.
- **`off`** — hide both windows; log still writes. One-shot `agent -p` forwards stay hidden.
- One-click `Watch-AgentHealth-*-*.cmd` and Desktop shortcuts are **`-Windows off`** (`Run-Hidden.vbs`). Legacy `*Resume*` names still pass `-New`.

Restricted ExecutionPolicy: use the `.cmd` wrappers (`-ExecutionPolicy Bypass`).

## Cursor TUI

Launch via `cursor-agent.ps1` and a **prompt file** (`launch-cursor-tui.ps1`, `-NoExit`). Never put the seed on `agent.cmd` / `cmd.exe` argv.

`create-chat` may fail (local session id only). `--resume` waits until a run succeeds.

If Composer never appears: print-only, no TUI relaunch storm. Hidden `agent -p` forwards stay available.

## `--new` prune

Only the **previous watch session** plus hung `forward-cursor.ps1` / orphan `worker-server`. Never Stop-Process fleet `Git task` / `long-running-background-tasks` or another TUI.

## IRC homes (watch only)

- `%USERPROFILE%\.agentic-irc-watch-cursor` (slot 1)
- `%USERPROFILE%\.agentic-irc-watch-cursor-2` … `-16` (next free on each launch)
- same pattern for `watch-grok`

Each systray / Watch-AgentHealth launch without `-IrcHome` binds the **next free
slot** (no live `-WatchWorker` on that home). Seats 2/3/4 are not blocked by
seat 1. State/log/worker pid are per-slot under
`~\.grok\agent-health\watch-{cursor|grok}-{N}\`.

Orphan prune on start is **this slot only**: hung `forward-cursor` under this
state dir, orphan `worker-server` nodes, and `irc_agent`/`irc_listen` on this
home when no other live watch worker owns it. Never kill another seat's worker
or IRC.

Nick `{machine}-{seatPid}` (watch worker PowerShell `$PID` / `coordinator.pid` seat=). Channels: `#{machine}` only (CAST IRON 2026-09-25; `#bobiverse` is for bob-{machine} ears, Jeeves and humans).

Forbidden: `.agentic-irc-cursor`, `cursor-2`, `.agentic-irc-bobiverse`. No `!bobiverse`. No UAT stamp.

Log: `%USERPROFILE%\Desktop\Watch-AgentHealth\Watch-AgentHealth.log` (slot 1) or `Watch-AgentHealth-{N}.log`.

Watch-seat agent behaviour: skill `watch-seat`.
