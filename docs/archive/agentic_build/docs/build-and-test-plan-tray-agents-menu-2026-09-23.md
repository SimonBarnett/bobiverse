<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/build-and-test-plan-tray-agents-menu-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build/test plan: tray Agents menu (2026-09-23)

FR: `docs/feature-request-tray-agents-menu-2026-09-23.md`.

## Build

1. `tools/Watch-BobTray.ps1`
   - Agent defs (Cursor/Grok): kind (`Watch-AgentHealth.cmd` arg) + app exe for
     the Desktop-parity icon.
   - `Get-BobTrayAgentImage` -> `Icon.ExtractAssociatedIcon` on the exe;
     fall back to the tray robot glyph when the exe is absent.
   - `ConvertTo-BobTrayGrayImage` (ColorMatrix) greys not-installed entries.
   - `Test-BobTrayAgentInstalled` = watch-seat cmd + agent exe both present.
   - `Invoke-BobTrayAgent`: installed -> `Start-BobTrayAgentWatch`
     (`Watch-AgentHealth.cmd <kind>`); else `Initialize-BobTrayAgentSetup`
     (`Install-AgentMonitor.ps1 -Agent <kind>`).
   - `Build-BobTrayAgentsMenu` populates the **Agents** submenu; rebuild on
     `DropDownOpening` so grey/enabled + icons stay current.
2. `tools/Install-AgentMonitor.ps1` -- clone/update AgentMonitor into
   `Desktop\Watch-AgentHealth`, copy its watch-seat skills into `~\.grok\skills`.
3. `.grok/skills/agent-monitor-setup/SKILL.md` -- owner skill; add to BT0 skills
   list; reference from `harvest-agent-skills` and `bob-fleet-tray`.
4. `docs/skill-harvest-log.md` -- dated note.

## Test (hermetic)

- `tools\Test-Pack.ps1`:
  - BT0 skills: `agent-monitor-setup` present with matching `name:`.
  - BT0l traySrc: `Text = 'Agents'`, `Build-BobTrayAgentsMenu`,
    `ExtractAssociatedIcon`, `ConvertTo-BobTrayGrayImage`, `Install-AgentMonitor`,
    `Watch-AgentHealth.cmd`; skill names the menu + setup; setup tool exists.
- Windows smoke (operator): recycle Watch-BobTray only; right-click ->
  **Agents**; installed agent icon matches Desktop shortcut and launches;
  uninstalled agent greyed and click runs setup.

## Do not

- Add a second NotifyIcon or a second dialog. Recycle Watch-BobTray only.
- Push origin/main for the harvest; open a PR. No UAT stamp.
