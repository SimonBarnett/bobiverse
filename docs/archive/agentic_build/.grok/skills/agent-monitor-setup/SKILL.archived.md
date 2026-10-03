<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path .grok/skills/agent-monitor-setup/SKILL.md, last changed 2026-09-24. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: agent-monitor-setup
description: >
  Install / initialise the AgentMonitor watch-seat (Cursor or Grok) from the
  Bob Fleet tray "Agents" menu, and via tools/Install-AgentMonitor.ps1. Use
  when the user says agents menu, tray agents, install watch seat, set up
  Cursor/Grok agent, agent not installed grey, initialise agent setup,
  Install-AgentMonitor, or /agent-monitor-setup. The watch-seat behaviour
  itself lives in the AgentMonitor repo skills (agent-monitor, watch-seat).
github: https://github.com/SimonBarnett/agentic_build
---

# Agent monitor setup (tray Agents menu)

The Bob Fleet tray (`tools/Watch-BobTray.ps1`, skill `bob-fleet-tray`) exposes
the two watch-seat agents as ONE context-menu item, **Agents**. Right-click the
tray robot, open **Agents**, then select which agent to launch. This replaces
having two separate desktop/tray icons.

## Menu entries

| Entry | Watch-AgentHealth arg | Icon source (same as Desktop shortcut) |
|-------|-----------------------|-----------------------------------------|
| Cursor | `cursor` **always `-New`** | Desktop `Cursor.lnk` IconLocation/TargetPath, else `%LOCALAPPDATA%\\Programs\\cursor\\Cursor.exe` |
| Grok | `grok` **always `-New`** | Desktop `Grok Bot.lnk`, else `%ProgramFiles%\\Grok Bot\\Grok Bot.exe`, else `%LOCALAPPDATA%\\Programs\\Grok Bot\\Grok Bot.exe` |

- **CAST IRON — always new (Simon 2026-09-23).** Tray Agents clicks, TipForm
  Cursor/Grok section icons, and Desktop agent links **always** pass `-New`
  (fresh session id + full skills + seed prompt). They must **never** resume
  a stored session. Explicit CLI `resume` is opt-in only for rare recovery.
- **CAST IRON — Cursor model auto (Simon 2026-09-23).** Tray / TipForm Cursor
  launches always pass `-Model auto` so Composer starts in Auto (not a sticky
  prior model). Grok has no `auto` model id; tray Grok uses the CLI default.
- **Icon parity.** Icons come from `ExtractAssociatedIcon` on the agent `.exe`,
  then plated on a light chip so dark glyphs stay visible on the dark TipForm /
  menu (badge fallback is a bright C/G chip). Desktop `.lnk` IconLocation
  points at the agent `.exe` (not a tiny broken `.ico`). Tray resolver must
  include **Program Files\\Grok Bot** and read Desktop `.lnk` first — see
  `bob-fleet-tray` § Agent shortcut icons.
- **Installed** = the agent `.exe` exists (`Resolve-BobTrayAgentExe` returns a
  real path). Click launches a **hidden** watch worker (`powershell
  -WindowStyle Hidden -File Watch-AgentHealth.ps1 -WatchWorker -Cursor|-Grok
  -New` and for Cursor `-Model auto`) so the watch console stays hidden but
  the agent TUI stays visible (do **not** pass `-Windows off`). Legacy
  `*-Resume` Desktop names still launch `-New` via `Run-Hidden.vbs`.
- **Not installed** = icon is greyed (desaturated, still visible). The entry
  stays clickable; clicking **initialises the setup**
  (`tools/Install-AgentMonitor.ps1 -Agent <cursor|grok>`), which deploys
  AgentMonitor and re-enables the entry.
- The dropdown rebuilds on open (`DropDownOpening`) so grey/enabled state and
  icons reflect the current install.

## Setup / initialise

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$repo\\tools\\Install-AgentMonitor.ps1" -Agent both
```

`Install-AgentMonitor.ps1`:

1. Clones (or `fetch` + `reset --hard`) `https://github.com/SimonBarnett/AgentMonitor`
   into `Desktop\\Watch-AgentHealth` (the Desktop shortcut target).
2. Copies the AgentMonitor watch-seat skills (`agent-monitor`, `watch-seat`)
   into `~\\.grok\\skills`.
3. Logs to `~\\.grok\\long-running-background-tasks\\install_agent_monitor.log`.

Idempotent: re-running updates the deploy in place.

## Skill harvest

This setup ships with the agentic_build skill harvest: `Copy-BobProjectSkills`
/ `Install-BobFleet` copy this `SKILL.md` into `~\\.grok\\skills`, and
`harvest-agent-skills` lists it. The watch-seat runtime contract stays in the
AgentMonitor repo skills; this skill only owns tray wiring + install.

## CAST IRON — IRC on systray launch (Simon 2026-09-23)

Tray **Agents** / TipForm Cursor|Grok clicks launch `Watch-AgentHealth.ps1`
which binds the **next free** `.agentic-irc-watch-*` / `-2` / `-3` … slot,
**Ensure-WatchIrcSeat** (starts `irc_agent` + `irc_listen`, JOINs `#bobiverse`,
`#{machine}`, `#agentic_irc`), and prunes orphan python/nodes for **that slot
only**. Opening seat 3/4 must not kill seat 1. The TUI agent receives IRC only
via monitor `FROM` forwards (skill `watch-seat`) — not by probing logs.

## CAST IRON — harvest MRB process when seating free agents (Simon 2026-09-24)

When tray Agents / Install-AgentMonitor sets up a free agent that may do MRB,
seed its instruction/context with skill `bob-mrb-worker` (STANDARD tests-first
PASS merge / FAIL one fix PR). Do not leave MRB process only in chat memory.

## Hard rules

- Not a Windows service. Recycle the tray (skill `bob-fleet-tray`) after menu
  code changes; do not add a second NotifyIcon.
- Do not point a watch seat at a forbidden IRC home (see `watch-seat`); the
  tray only passes `cursor` / `grok`, letting AgentMonitor pick the watch home.
- No secrets. No UAT stamp.

## Plan menu (Simon 2026-09-24)

Bob Fleet tray **Plan > Grok|Cursor** (top-level, same level as **Agents**) starts a visionary **plan seat**
(not a watch seat): syncs `skills-visionary`, opens the agent in plan mode, no
IRC / no `Watch-AgentHealth`. See `bob-fleet-tray`.