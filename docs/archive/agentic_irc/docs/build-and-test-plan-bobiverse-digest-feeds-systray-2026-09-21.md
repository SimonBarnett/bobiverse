<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/build-and-test-plan-bobiverse-digest-feeds-systray-2026-09-21.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: `!bobiverse` JSON feeds full Bob systray

**Date:** 2026-09-21  
**Repo:** SimonBarnett/agentic_irc  
**FR:** `docs/feature-request-bobiverse-digest-feeds-systray-2026-09-21.md`  
**Sister consumer:** SimonBarnett/agentic_build (same slug FR + plan)  

## Goals

1. Chair `!bobiverse` whisper JSON (`BOB DIGEST v1 i/n`) carries the **full
   systray dataset** (do not gut the card; do not ship presence-only).
2. Additive: top-level **`cursor_pools`** (one entry per Cursor quota seat).
3. Whisper-only; no POINT firehose; no secrets.

## Non-goals

- HTTP GET digest. Halloy changes. Gutting TipForm fields.
- Implementing agentic_build ingest (sister PR). Keep JSON shape stable for
  that consumer.

## Locked constants

- Registry ids: `flamingo`, `marchhare`, `ionos`, `ce-priority-dev1`
- Chair nick: `Jeeves` / `digest.json` `chairNick`
- Chunk prefix: `BOB DIGEST v1 i/n`
- Refresh verb: `!bobiverse` only (no `!report` write path)

## Phases

### P0 — Shape

Document and implement digest object fields sufficient for
`Get-BobTrayHover` peers + `cursor_pools`:

Per machine (minimum): `id`, `nick`, `shop`, `online`, `status`,
`working_on`, `workers`, `weekly`, `period_end`, `lastSeen`, `running`,
`queued`, `jobs[]` (repo/sha/model/description/state/run_time when known),
plus any fields the live card already shows.

Top-level: `v`, `ts`, `briefer`/`chairNick`, `cursor_pools[]`
(seat id/label, remaining or used %, period_end/reset, overage if known).

Exit: offline unit tests assert keys present on `build_digest_object` /
`format_digest_whisper_lines`.

### P1 — Populate

Merge webhook + local peer/status sources so chair digest is not
presence-only. Prefer existing `bobreport` / POST `reportUrl` paths.
Do not reintroduce Watch POINT.

Exit: pytest with fixtures; English brief still works; JSON chunks parse.

### P2 — Pack

`tests/` cover: full digest round-trip, chunk reassembly, no secret leak,
cursor_pools length ≥ 1 when seats configured in fixture.

## Definition of done (first ticket)

- PR against `main` (never push main).
- FR doc linked in PR body.
- Pytest green offline.
- Kickoff: implement P0–P2 for this FR only; open PR; paste test summary.

## Kickoff prompt (Start-BobBuild -Goal)

Read `docs/feature-request-bobiverse-digest-feeds-systray-2026-09-21.md`
and this plan. Implement P0–P2 on a `work/<job>` branch. Do not gut tray
field requirements. Do not push `main`. Open a PR. Never stamp UAT.
