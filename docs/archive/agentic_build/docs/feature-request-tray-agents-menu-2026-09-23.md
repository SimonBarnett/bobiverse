<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-tray-agents-menu-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: tray Agents menu (two icons -> one menu, desktop-parity, setup)

**Date:** 2026-09-23
**Repo:** https://github.com/SimonBarnett/agentic_build
**Source repo (watch seat):** https://github.com/SimonBarnett/AgentMonitor
**Raised by:** Simon
**Skills:** bob-fleet-tray, agent-monitor-setup, harvest-agent-skills

## Ask (Simon 2026-09-23)

The two icons should be a menu item on the systray called **Agents**; then
select which. The icon should be the **same as the Desktop item**. If an agent
is **not installed** it should be **grey**, and clicking it should **initialise
the setup**. Add the setup in the **skill harvest**. Draft PR.

## LOCKED

1. One tray context-menu item **Agents** replaces the two separate icons; its
   submenu lists the watch-seat agents (Cursor, Grok) and you select which.
2. Each entry uses the **same icon as its Desktop shortcut** -- extracted from
   the agent app exe (`%LOCALAPPDATA%\Programs\cursor\Cursor.exe`,
   `%LOCALAPPDATA%\Programs\Grok Bot\Grok Bot.exe`), matching AgentMonitor
   `shortcuts/*.lnk` IconLocation. Not the tray robot glyph.
3. Not installed -> icon is **greyed**; the entry stays clickable and clicking
   **initialises the setup** (`tools/Install-AgentMonitor.ps1`).
4. Installed -> clicking launches `Watch-AgentHealth.cmd <cursor|grok>`.
5. The setup ships with the **skill harvest** (`agent-monitor-setup` skill +
   `Copy-BobProjectSkills` / `Install-BobFleet`; `harvest-agent-skills` points
   at it).
6. Additive tray UI only; keep the existing card, Status/Ack/Log/Restart/Exit,
   single NotifyIcon, single instance. Not a Windows service. No UAT stamp.

## UNKNOWN (do not invent)

- Exact per-machine Desktop shortcut icon paths beyond the two exe paths above
  (AgentMonitor playbook marks these UNKNOWN). The tray falls back to the tray
  robot glyph (greyed) when an exe is absent.

## Acceptance

- A1: Tray context menu shows **Agents** with Cursor + Grok entries.
- A2: Installed entry icon matches the Desktop shortcut app icon; click launches
  the watch seat.
- A3: Not-installed entry is greyed; click runs `Install-AgentMonitor.ps1`.
- A4: `agent-monitor-setup` skill in `.grok/skills`, in BT0 skills list, and
  referenced by `harvest-agent-skills`.
- A5: Test-Pack BT0l asserts the Agents menu, icon parity, grey state, setup.
- A6: No UAT stamp; harvest is a PR, not a commit to main.
