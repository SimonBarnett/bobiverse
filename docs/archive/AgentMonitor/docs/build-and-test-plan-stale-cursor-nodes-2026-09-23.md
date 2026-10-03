<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/build-and-test-plan-stale-cursor-nodes-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build/test plan: stale cursor-agent nodes (#30)

1. Read the FR. Do not kill fleet `Git task` nodes or other TUIs on `--new`.
2. After Composer OOM / missing node: print-only, no TUI relaunch storm, no second `create-chat`.
3. `Test-CursorAgentForwardBusy` must see `forward-cursor.ps1` even without `--resume`.
4. Open a PR linking the issue. Do not stamp UAT.

## Checks

- Parser: `Watch-AgentHealth.ps1` has no parse errors.
- Grep: no `Stop-CursorAgentNodesExceptSession` and no `relaunch visible TUI`.
- Protected: command lines containing `Git task ` or `long-running-background-tasks` are skipped.
