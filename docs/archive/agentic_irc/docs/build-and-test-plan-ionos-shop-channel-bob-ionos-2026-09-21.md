<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/build-and-test-plan-ionos-shop-channel-bob-ionos-2026-09-21.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: `#ionos` shop — `bob-ionos` + ionos workers

**FR:** `docs/feature-request-ionos-shop-channel-bob-ionos-2026-09-21.md`

## Phase 1 — Prove JOIN path

- Trace `irc_agent` reconnect: `_pending_joins`, multi-channel `JOIN`, 366/JOIN echo.
- Fix if `bob-ionos` ever runs with a single-channel list on ionos.
- Confirm Ergo has `#ionos` (operator doc note in `bobiverse-ionos-ircd.md` if needed).

## Phase 2 — Worker shop JOIN on ionos

- Find where git workers start `irc_agent` (agentic_build bridge / worker home).
- Ensure machine id `ionos` → worker nick `w-io-<pid>` and shop `#ionos`.

## Phase 3 — Tests + docs (shop JOIN)

- Pytest: `channels_for_nick('bob-ionos', '#bobiverse')` → `#bobiverse`, `#ionos`.
- Pytest: worker nick → `#ionos` only.
- Update `.grok/skills/bob-irc/SKILL.md` (and harvest to agentic_build if required).

## Phase 4 — Grok-talk enqueue on ionos (merged #68)

- Extend `should_enqueue` / fuel gate: weekly > 0 **or** Cursor remaining > 0
  (test double for remaining; no `cursor_label` as fuel).
- ACK line must not say `cannot grok-talk` when enqueue fires.
- Align `docs/grok-talk-envelope-v1.md` and skills. No `grok_talk_worker.py`.
- Pytest AC1–AC3 from FR (same mention rules as #56).

## Evidence for MRB

- `pytest -q` relevant files.
- Redacted `irc.log` snippet: two JOINs for `bob-ionos` after Watch recycle.
- No live Halloy required in CI.
