<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/build-and-test-plan-composer-tui-launch-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build/test plan: Composer TUI launch (#34)

1. Read issue #34 and this FR. Do not put the seed on `agent.cmd` `Start-Process -ArgumentList`.
2. Write `launch-cursor-tui.ps1`; start it with `powershell.exe -NoExit -File`; `cursor-agent.ps1 -- $prompt` from the prompt file.
3. Miss-node and snapshot log lines say low commit / OOM only when commit is actually low.
4. Open a PR linking the issue. Do not stamp UAT.

## Checks

- Parser: `Watch-AgentHealth.ps1` has no parse errors.
- Grep: `Start-CursorInteractiveTui` writes `launch-cursor-tui.ps1` and starts `powershell.exe` `-File`.
- Grep: no `Write-CursorAgentProcessSnapshot -Reason` containing `OOM` unless that path also gated on `Get-CommitHeadroomGb` low commit.
