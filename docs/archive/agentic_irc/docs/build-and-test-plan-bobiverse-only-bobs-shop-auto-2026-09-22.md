<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/build-and-test-plan-bobiverse-only-bobs-shop-auto-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build/test — bobiverse-only bobs + talk-seat shop (2026-09-22)

1. `python -m pytest tests/test_bobreport.py::test_channels_for_nick -q`
2. Manual: `Start-TalkSeat.ps1 -MachineId marchhare` → nick `marchhare-$PID` JOINs `#marchhare` only (no `#bobiverse` in irc.log 001/JOIN).
3. `bob-marchhare` still JOINs `#bobiverse,#marchhare`.
4. Optional: `-Channel '#marchhare,#agentic_irc'` for FR talk without fleet.
