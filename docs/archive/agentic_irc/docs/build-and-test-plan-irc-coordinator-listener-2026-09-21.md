<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/build-and-test-plan-irc-coordinator-listener-2026-09-21.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: IRC coordinator listener

**FR:** `docs/feature-request-irc-coordinator-listener-2026-09-21.md`

## Goals

Confirm listener MUST is in the repo. Fill any hole vs LOCKED/AC. PR.

## Non-goals

Live Ergo. Enabling grok-talk. Watch-Bobiverse grok.exe. Recycle BobFleet-*.
UAT stamp (Bob only).

## Phases

1. Read FR + harvest `a8c2daa`. Diff vs LOCKED 1-5 and AC1-3.
2. If already green: keep files; add only missing docs/tests. Do not revert.
3. If a hole: implement on a work branch. Do not push main as implementer.
4. Pytest: `python -m pytest tests/test_irc_listen.py tests/test_wire.py tests/test_bobtalk.py -q`
5. Open PR to `main`.

## Locked

`MENTION_COOLDOWN` unchanged. Line cap 350 stays skill text. Two homes.
`looks_like_secret` drops inbound. No `password=` / `XAI_API_KEY=` assignments.

## Done

PR open. AC1-3 true on the head SHA. Offline pytest green.
