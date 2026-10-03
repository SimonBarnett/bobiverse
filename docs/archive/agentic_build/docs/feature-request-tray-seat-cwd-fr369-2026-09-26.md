<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-tray-seat-cwd-fr369-2026-09-26.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR #369: tray watch seats use per-machine bob-seat-work (not live C:\ai)

## Problem

`Start-BobTrayAgentWatch` passed `-Cwd`, but `Get-BobTrayWatchWorkspace` preferred existing `\ai` roots (`C:\ai`), so seats worked inside live `agentic_build` / Jeeves trees.

## Expected

- Default: `C:\bob-seat-work\<machine>` (created if missing)
- Configurable: `BOB_SEAT_WORK` (exact path) or `BOB_SEAT_WORK_ROOT` (parent)
- Never resolve seat cwd to a live `\ai` tree
- Tray launch always includes `-Cwd <seat-work>`

## Tests

`BT102`, `BT369` in `tools/Test-Pack.ps1`
