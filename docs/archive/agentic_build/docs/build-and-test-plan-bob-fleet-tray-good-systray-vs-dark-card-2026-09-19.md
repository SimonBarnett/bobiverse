<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/build-and-test-plan-bob-fleet-tray-good-systray-vs-dark-card-2026-09-19.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build-and-test plan: tray good tip vs dark card conflict

**FR:** `docs/feature-request-bob-fleet-tray-good-systray-vs-dark-card-2026-09-19.md`

## Steps

1. Reproduce on ionos with Watch-BobTray: hover vs click; note z-order / auto-show of dark card vs NotifyIcon tip (`P+ idle …`).
2. Read Get-BobTrayHover / Watch-BobTray and prior park-once / dark-card commits.
3. Implement: default path keeps good tip visible; dark fleet card only on explicit click (or equivalent); auto-dismiss; no sticky cover of clock tray.
4. Align with in-progress all-machines peer-peek WIP if present on working tree — do not leave half-merged hover behaviour.
5. Test-Pack / manual UAT; recycle Watch-BobTray; screenshots into docs/screenshots/.
6. Commit/push; Bob hostile MRB (Simon-raised).

## Success

FR acceptance criteria green; good tip usable without fighting the dark card.
