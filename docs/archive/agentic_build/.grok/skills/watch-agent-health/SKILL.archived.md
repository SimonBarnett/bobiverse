<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path .grok/skills/watch-agent-health/SKILL.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: watch-agent-health
description: >
  Create a persistent Cursor/Grok watch seat with Watch-AgentHealth only.
  Preferred IRC wake path (AgentMonitor forwards FROM; do not arm in-session
  listen.stdout.log ^FROM TSR). Use when starting a new Cursor/Grok worker
  on a box, extra client, watch-cursor-2, hidden shortcut, Start-BobWatchWorker,
  tray Agents, or Simon says this is the only way to create build workers /
  preferred IRC receive.
---

# Watch-AgentHealth (preferred seat + IRC wake)

A **watch seat** is a persistent Cursor or Grok session with its own
`.agentic-irc-watch-*` home, its own `irc_agent`, and its own `irc_listen`.
Product: `SimonBarnett/AgentMonitor`. Fleet copy: `tools/Watch-AgentHealth`.
Launcher: `tools/Start-BobWatchWorker.ps1`. Tray: skill `agent-monitor-setup`.

## CAST IRON (Simon 2026-09-23) — preferred IRC wake

**Preferred way to receive IRC in a Cursor/Grok session:** start via
Watch-AgentHealth. The monitor tails this slot's `irc.log` and forwards
`FROM` into the session. That avoids burning Cursor turns on `#bobiverse`
spam (`!bobiverse`, GIT firehose) from an in-session
`Get-Content -Wait` / `notify_on_output` on every `^FROM `.

If Simon started this session with a watcher:

- Own a `.agentic-irc-watch-*` home only (skill `watch-seat`).
- Act on monitor payloads. Do **not** arm a second IDE TSR on
  `listen.stdout.log` / `irc.log`.
- IRC wire facts stay in `agentic-irc` (Listener + wake).

Legacy talk-seat IDE TSR (`Start-TalkSeat` + notify on `^FROM `) is
fallback only when no AgentMonitor — see `agentic-irc`.

## CAST IRON — only way to create a build worker

**This is the only way to create a build worker.**

Do **not** create a worker with:

- `Start-TalkSeat.ps1` / `cursor-2` talk-seat home
- `start_worker_irc_agent.py` as the agent
- a raw second Composer TUI + manual `irc_agent`
- `Start-BobCursor.ps1` / `cursor-agent -p` (that is a one-shot **job**, not a seat)
- `Start-BobWorker` grok.exe `-p` (same: job, not a seat)

Talk seats (`~\.agentic-irc-cursor`, `cursor-2`, `{machine}-{pid}`) stay
talk seats. Shop `w-*` nicks on a one-shot job PID stay issue #70 shop
presence. Neither is how you add a build-worker seat.

## Create

Hidden (shortcuts and fleet default): no watch console, no TUI. Log still writes.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\ai\agentic_build\tools\Start-BobWatchWorker.ps1 -Kind cursor
powershell -NoProfile -ExecutionPolicy Bypass -File C:\ai\agentic_build\tools\Start-BobWatchWorker.ps1 -Kind grok
```

Or Desktop shortcut / `Watch-AgentHealth-Cursor-New.cmd` (already `-Windows off`).
Main `Watch-AgentHealth.cmd cursor new` from a terminal is still visible unless `off`.
Tray **Agents** menu: skill `agent-monitor-setup`.

Each launch binds the **next free slot** (`.agentic-irc-watch-cursor`, `-2`, …).
Does not restart a live seat. One seat = one home = one `irc_listen` = one
`irc.log`. Sharing a listener copies every PRIVMSG into every connected client.

When the TUI/worker exits: that slot QUITs IRC. Start another client; do not
reconnect the same one.

## Install

`Install-BobFleet` copies `tools/Watch-AgentHealth` to
`%USERPROFILE%\Desktop\Watch-AgentHealth` (cmds + script + shortcuts).
`Install-AgentMonitor.ps1` (skill `agent-monitor-setup`) deploys from
`SimonBarnett/AgentMonitor` and copies `agent-monitor` + `watch-seat` into
`~\.grok\skills`.

Canonical monitor updates stay in `SimonBarnett/AgentMonitor`. Re-copy after an
AgentMonitor pull if the fleet snapshot is behind.

## Skills

Monitor vs seat: AgentMonitor `agent-monitor` + `watch-seat`.
IRC wire / wake preference: `agentic-irc`.
Jobs still use `start-bob-cursor` / `Start-BobWorker`.
No UAT stamp.
