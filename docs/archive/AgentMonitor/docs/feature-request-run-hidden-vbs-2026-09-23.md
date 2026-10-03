<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/feature-request-run-hidden-vbs-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: shortcut workers launch with no console (Run-Hidden.vbs)

https://github.com/SimonBarnett/AgentMonitor/issues/66

Push `48f5665` on stale branch `issue-32-tui-launch-ps1`. PR pending. No UAT.

Sibling #61 (`14198d5`) hid the worker via `start powershell -WindowStyle Hidden`. That still flashes a console. This FR removes the flash.

## LOCKED

1. Shortcut `.cmd` files launch via `wscript.exe //nologo Run-Hidden.vbs` with `-Windows off`.
2. `Run-Hidden.vbs` runs `powershell.exe -WindowStyle Hidden -File Watch-AgentHealth.ps1` with `WScript.Shell.Run` style 0 (no window).
3. Main `Watch-AgentHealth.cmd` stays visible unless the operator passes `off`.
4. Playbook / `agent-monitor` skill mention no-console / VBS launch for shortcuts.

## Gap vs `14198d5` (main after #61)

Shortcut `.cmd` still uses `start "" powershell.exe ... -WindowStyle Hidden`, which can flash a console.

## Acceptance

| ID | Gate |
|----|------|
| A1 | `Watch-AgentHealth-*-New.cmd` and `*-Resume.cmd` (cursor + grok) call `wscript.exe //nologo Run-Hidden.vbs`, not `start powershell`. |
| A2 | `Run-Hidden.vbs` exists and launches powershell hidden (`WindowStyle Hidden` + `Run` style 0). |
| A3 | Main `Watch-AgentHealth.cmd` without `off` remains a visible `-NoExit` console. |
| A4 | `off` on the main `.cmd` still hides watch + TUI. |
| A5 | Playbook and `agent-monitor` skill match A1–A4. |
| A6 | No UAT stamp. |
