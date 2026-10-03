<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/build-and-test-plan-bobiverse-digest-feeds-systray-2026-09-21.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: ingest tray-complete `!bobiverse` JSON into systray

**Date:** 2026-09-21  
**Repo:** SimonBarnett/agentic_build  
**FR:** `docs/feature-request-bobiverse-digest-feeds-systray-2026-09-21.md`  
**Sister protocol:** SimonBarnett/agentic_irc (same slug FR + plan)  

## Goals

1. Watch / tray refresh asks `!bobiverse` and ingests **`BOB DIGEST v1` JSON**
   into `bob-peers` (+ cursor pool cache) so TipForm keeps **all current
   card data**.
2. Additive UI only: separated **Cursor quota** bars (#91) fed from
   digest `cursor_pools`.
3. Do **not** shrink the systray to presence-only fields.

## Non-goals

- POINT firehose. `Install-BobFleet` churn. HTTP GET digest.
- Replacing Grok weekly machine bars with Cursor bars.

## Phases

### P0 — Ingest DIGEST JSON

Extend `Import-BobIrcTrayPull` (or sibling) to parse chair whispers
`BOB DIGEST v1 i/n`, reassemble JSON, write `bob-peers\<id>.json` with
full tray fields + apply `cursor_pools` via existing seat/pool cache
helpers.

Keep `BOB TRAY v1` path working if still present.

Exit: Test-Pack fixture whisper → four peer files + pools cache.

### P1 — Hover / card

`Get-BobTrayHover` / `Watch-BobTray`: after ingest, paint no less than
today’s card + one bar per Cursor pool. Job lines use digest jobs
(repo/sha/model/description); never `?` when sha present.

Exit: Test-Pack hover assertions; skill `bob-fleet-tray` one-paragraph
refresh = `!bobiverse` JSON.

### P2 — Watch wiring

Confirm `Watch-Bobiverse` ~120s pull uses the new ingest. No POINT
required for peer freshness in tests.

## Definition of done (first ticket)

- PR against `main` (never push main).
- Depends on sister JSON shape; if irc PR not merged, pin expected shape
  from sister FR/plan in fixtures.
- Test-Pack cases green offline.
- Open PR; paste summary; never stamp UAT.

## Kickoff prompt (Start-BobBuild -Goal)

Read `docs/feature-request-bobiverse-digest-feeds-systray-2026-09-21.md`
and this plan. Implement P0–P2 on `work/<job>`. Do not gut TipForm.
Do not push `main`. Open a PR.
