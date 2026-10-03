<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/build-and-test-plan-lnk-target-cmd-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: .lnk target .cmd (#68)

## MUST
1. Five listed `shortcuts/*.lnk` target matching `Watch-AgentHealth-*-*.cmd`, not `powershell.exe`.
2. No `shortcuts/*.lnk` targets `powershell.exe` or `wscript.exe`.
3. Four shortcut `.cmd` files and `Run-Hidden.vbs` (if present) unchanged in meaning.
4. No UAT stamp.

## Checks
- COM-read each `.lnk` TargetPath basename is `*.cmd`.
- `git diff` does not change `Watch-AgentHealth*.cmd` or `Run-Hidden.vbs`.
