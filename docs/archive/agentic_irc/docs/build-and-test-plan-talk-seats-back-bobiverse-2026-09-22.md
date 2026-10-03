<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/build-and-test-plan-talk-seats-back-bobiverse-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: talk seats back on `#bobiverse`

**Date:** 2026-09-22  
**Repo:** SimonBarnett/agentic_irc  
**FR:** docs/feature-request-talk-seats-back-bobiverse-2026-09-22.md  
**Issue:** https://github.com/SimonBarnett/agentic_irc/issues/108  
**MRB:** https://github.com/SimonBarnett/agentic_irc/issues/109  

## Goals

Restore talk-seat fleet membership per issue #108 after #99 shop-only policy. Worker `w-*` and Jeeves rules stay as in #98 / #100.

1. `channels_for_nick`: `{machine}-{pid}` → `#bobiverse` + `#{machine}` + extras (TS1–TS3).
2. `Start-TalkSeat.ps1` default `#bobiverse,#$mid,#agentic_irc` (TS4).
3. Park FR + this plan; mark #98 / #100 shop-only talk-seat LOCKED superseded in `/docs`.
4. `agentic-irc` skill rooms table matches LOCKED (TS5).

## Non-goals

Mode 3 PIN on `#bobiverse`. Workers on fleet. #70, #88, #102 scope. ChanServ; remote auto-PART; UAT stamp. Never push `main`. Never merge in-worker.

## Build

1. Land `docs/feature-request-talk-seats-back-bobiverse-2026-09-22.md` and this plan (linked to #108 / #109).
2. Supersede talk-seat fleet clauses in `docs/feature-request-machine-channel-bobosphere-bobs-only-2026-09-22.md` and `docs/feature-request-bobiverse-only-bobs-shop-auto-2026-09-22.md` (keep `w-*` shop-only and Jeeves-all-shops).
3. `scripts/bobreport.py`, `scripts/Start-TalkSeat.ps1`, `.grok/skills/agentic-irc/SKILL.md`.

## Test

1. `python -m pytest tests/test_bobreport.py::test_channels_for_nick -q` — TS1–TS3.
2. Grep `Start-TalkSeat.ps1` default channel for `#bobiverse` — TS4.
3. Grep skill: talk seats JOIN fleet + shop; `w-*` shop only; Mode 3 not on `#bobiverse` — TS5.
4. `python -m pytest -q` green.

## Done when

PR open for Bob MRB on issue #109; acceptance TS1–TS5 satisfied in tree. No merge from this worker.
