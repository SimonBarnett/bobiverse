<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-systray-start-agent-visible-tui-2026-09-23.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: systray start agent — watcher hidden, TUI visible

## Summary
Simon (agentic_irc #181, 2026-09-23): when Agents menu starts Cursor/Grok from the box systray, the **agent watcher must stay hidden** but the **TUI agent console must be shown** so he can interact with it.

## Gap vs current tree
`Start-BobTrayAgentWatch` in `tools/Watch-BobTray.ps1` runs `Watch-AgentHealth.cmd <kind>`. That path uses `powershell -NoExit` (visible watch console). Shortcut `off` / `-Windows off` hides **both** the watch console and the agent TUI.

Needed: launch `Watch-AgentHealth.ps1 -WatchWorker -Cursor|-Grok` with the **watch process** `WindowStyle Hidden` (or equivalent) and **without** `-Windows off`, so `AgentTuiWindowStyle` stays `Normal`.

Do not change one-click Desktop shortcut `*-New.cmd` / `*-Resume.cmd` semantics (those stay fully hidden via `Run-Hidden.vbs`).

## Acceptance
| ID | Criterion |
|----|-----------|
| A1 | Systray Agents → Cursor/Grok starts a watch worker with no watch console window. |
| A2 | The agent TUI (Composer / Grok) opens visible (Normal), not Hidden. |
| A3 | Launch does not pass `-Windows off`. |
| A4 | Shortcut `.cmd` `off` / `Run-Hidden.vbs` paths unchanged. |
| A5 | `Test-Pack.ps1` covers the tray launch args (grep/assert) for A2–A3. |

## Out of scope
- Recycle flamingo/ionos from DEV1.
- Changing IRC webhook / private-message routing.
