<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/feature-request-composer-tui-launch-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: Composer TUI launch via cursor-agent.ps1 prompt file (issue #34)

https://github.com/SimonBarnett/AgentMonitor/issues/34

**MRB home:** [Issue #34](https://github.com/SimonBarnett/AgentMonitor/issues/34). **Land:** [PR #33](https://github.com/SimonBarnett/AgentMonitor/pull/33) (`ed6aa0c`). No source PDF. No UAT.

Watch spawned the Composer TUI through `agent.cmd` + `Start-Process -ArgumentList` including the seed prompt. `cmd.exe` truncates on spaces, so Composer exited immediately and the log blamed OOM.

## LOCKED (issue #34)

1. Launch writes `launch-cursor-tui.ps1` and runs `cursor-agent.ps1 -- $prompt` from a file (`powershell.exe -NoExit -File`).
2. The seed is not placed on `agent.cmd` / `Start-Process -ArgumentList`.
3. The monitor log says low commit / OOM only when commit is actually low (`Get-CommitHeadroomGb`).
4. No UAT stamp.

## Gap vs `c48ab3f`

`Start-CursorInteractiveTui` used `Start-Process -FilePath $AgentCmd` (`agent.cmd`) with the seed text on `-ArgumentList` after `--`. The miss-node line said `OOM or bad session`. The failure snapshot said `agent.cmd OOM or instant exit` even when commit was not low.

## Acceptance

| ID | Gate |
|----|------|
| A1 | `Start-CursorInteractiveTui` writes `launch-cursor-tui.ps1` and starts `powershell.exe -NoProfile -ExecutionPolicy Bypass -NoExit -File` that script. The script invokes `cursor-agent.ps1` with `-- $prompt` read from the prompt file. Not `agent.cmd` + seed on `Start-Process -ArgumentList`. |
| A2 | Every operator-visible miss-node / failure line (including `Write-CursorAgentProcessSnapshot -Reason`) says low commit or OOM only when `Get-CommitHeadroomGb` shows low commit. A snapshot with tens of GB free must not say `agent.cmd OOM`. |
| A3 | No UAT stamp. |

UNKNOWN: exact commit flamingo needs before a visible Composer TUI stays up (same UNKNOWN as #22 / #30).
