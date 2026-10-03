<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/build-and-test-plan-dispatcher-skip-fix-leftover-fail-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: dispatcher skip FIX on leftover FAIL (#228)

**Issue:** https://github.com/SimonBarnett/agentic_build/issues/228  
**FR:** `docs/feature-request-dispatcher-skip-fix-leftover-fail-2026-09-23.md`

## Scope

`tools/Bob-BuildLoop.ps1` `wait_mrb` + `tools/Start-BobBuildLoop.ps1` close handler.

## Tests (off-DEV, no live GitHub)

| ID | Case |
|---|---|
| BT228a | MRB FAIL + loop PR MERGED → `close_leftover_fail`, no FIX goal, close comment links PR |
| BT228b | MRB FAIL + loop PR OPEN → `start_fix` with Required fixes |
| BT228c | `-Once -TestWorld` loop invokes `-TestClose`, no `TestStartBuild` |
| BT228d | Leftover FAIL + MERGED + FR CLOSED → DONE, finish/pull hooks, no FIX |
| BT228e | Leftover FAIL + MERGED + FR PASS-nits merge comment → DONE, finish hook |

Run: `powershell -File tools/Test-Pack.ps1` (full pack) or grep `BT228` in output.

## Acceptance mapping

- A1/A2 → BT228a, BT228c  
- A3 → BT228b  
- LOCK 3 → BT228d, BT228e  
