<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/build-and-test-plan-bob-fleet-tray-per-machine-weekly-bars-2026-09-20.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build-and-test plan: per-machine weekly bars + IRC fleet status

**FR:** `docs/feature-request-bob-fleet-tray-per-machine-weekly-bars-2026-09-20.md`

## Steps

1. Read Get-BobTrayHover, Get-BobWeeklyRemaining, Watch-BobTray, bob-fleet-peer-peek, agentic_irc Mode 3 status patterns.
2. Refactor hover model: each machine tile includes `weeklyRemainingPct` from that host’s seat (local billing log or IRC-published snapshot).
3. Replace bogus unreachable with irc-fallback when peek fails but IRC status exists.
4. Fix flaky ShowParkedAt / click card reliability without MouseMove auto-show.
5. Test-Pack + UAT screenshots; commit/push; recycle trays.

## Success

FR acceptance green; flamingo build job completes with push.
