<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/feature-request-lnk-target-cmd-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: repo shortcuts/.lnk that call powershell.exe still flash a console

https://github.com/SimonBarnett/AgentMonitor/issues/68

Parked from MRB of #66 / SHA `48f5665`. Not a red gate on #66 A1–A6 (those name the four `.cmd` files). No UAT.

## LOCKED

1. Every `shortcuts/*.lnk` targets the matching `Watch-AgentHealth-*-*.cmd` wrapper (Desktop copy convention may stay `C:\Users\simon\Desktop\Watch-AgentHealth\*.cmd`).
2. No `shortcuts/*.lnk` targets `powershell.exe` or `wscript.exe` directly.
3. VBS / no-console launch stays in the `.cmd` files (`Run-Hidden.vbs`). Do not duplicate the VBS argv on the `.lnk`.
4. Do not break the four `.cmd` files or `Run-Hidden.vbs` from #66.
5. No UAT.

## Gap vs `14198d5` (main after #61 / #63)

These still invoke `powershell.exe -WindowStyle Hidden -File Watch-AgentHealth.ps1` and can flash a console even after the `.cmd` files use `wscript` + `Run-Hidden.vbs`:

- `shortcuts/Watch-Agent Cursor New.lnk`
- `shortcuts/Watch-Agent Cursor Resume.lnk`
- `shortcuts/Watch-Agent Grok New.lnk`
- `shortcuts/Watch-Agent Grok Resume.lnk`
- `shortcuts/Watch-AgentHealth-Grok-Resume.lnk`

The spaced-name set (`Watch AgentHealth - *.lnk`) already targets the `.cmd` files. Keep that pattern.

SHA `48f5665` rewrote every `.lnk` to `wscript.exe` + `C:\Users\simon\Desktop\Watch-AgentHealth\Run-Hidden.vbs` + `.ps1`. That skips the `.cmd` wrappers, hardcodes a machine Desktop path, and conflicts as binary vs main. Not the fix.

## Acceptance

| ID | Gate |
|----|------|
| A1 | The five `.lnk` files listed above target the matching `.cmd`, not `powershell.exe`. |
| A2 | No `shortcuts/*.lnk` has target `wscript.exe` or `powershell.exe`. |
| A3 | Four shortcut `.cmd` files and `Run-Hidden.vbs` unchanged in meaning (#66 A1–A2 stay green). |
| A4 | No UAT stamp. |
