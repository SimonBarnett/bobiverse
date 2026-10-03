<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/build-and-test-plan-systray-cursor-groups-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: systray Cursor groups + live IRC agents

**Date:** 2026-09-22
**Repo:** SimonBarnett/agentic_build
**FR:** docs/feature-request-systray-cursor-groups-2026-09-22.md
**Issue:** https://github.com/SimonBarnett/agentic_build/issues/151

## Goals

1. TipForm shows at least three Cursor groups: grok chat, high cost models,
   low cost models. RTFM Cursor Spending for field mapping. Do not invent %.
2. Live IRC agents (bob-* and {machine}-{seatPid} in NAMES / digest workers)
   paint as running, not idle/offline.
3. Additive only. Do not gut machine tiles, weekly bars, jobs_text, digest.

## Non-goals

- UAT stamp. Push/merge main. Other Models as MRB fuel.
- Inventing API field names. Shrinking the card.

## Phases

### P0 — Map groups (RTFM)

Read Cursor Spending meters. Map three group remaining % into hover JSON
(per seat or equivalent). Fixture if live schema is unknown — do not guess
production numbers.

Exit: documented mapping in box-usage / bob-fleet-tray; fixture keys exist.

### P1 — Paint groups

Watch-BobTray + Get-BobTrayHover: three labelled group bars. No single
merged Cursor Models row as the only Cursor row.

Exit: Test-Pack hermetic fixture paints three labels; no live billing HTTP.

### P2 — Live agents

Hover/tiles list talk seats and bob-* that digest/NAMES say are present.

Exit: fixture NAMES/digest workers => jobs_text or tile not "no jobs" /
offline for those nicks.

### P3 — PR

Open PR from work branch. Never push main. Never merge. Paste Test-Pack
summary. Bob chairs MRB on #151.

## Kickoff (Start-BobBuild -Goal)

Read docs/feature-request-systray-cursor-groups-2026-09-22.md and
docs/build-and-test-plan-systray-cursor-groups-2026-09-22.md. Implement
P0-P2 for issue 151. Open a PR. Never push main. Never merge. Do not
stamp UAT. Do not set an API key environment variable. PR model:
composer-2.5 (or build0.1 / grok-4.5). Never Other Models.
