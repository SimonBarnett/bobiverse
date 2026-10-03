<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/build-and-test-plan-talk-seat-survival-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: talk-seat survival (#90)

**Date:** 2026-09-22
**Repo:** SimonBarnett/agentic_irc
**FR:** docs/feature-request-talk-seat-survival-2026-09-22.md
**Issue:** https://github.com/SimonBarnett/agentic_irc/issues/90

## Goals

Simon: two processes per machine except dev; the second failed on each. Fix Start-TalkSeat / Start-IrcTsr so the second seat survives.

1. Detached irc_listen by default (survives Cursor shell; optional listen.stdout.log).
2. Hard fail if Start-TalkSeat targets a live other-nick home (no steal, no kill other listen).
3. Seat host lifecycle explicit (no orphan agent with empty listen).
4. Tests lock 1-2. PR only. Never push main. No UAT stamp.

## Non-goals

killproc salvage docs. Watch-Bobiverse / bob-* recycle. Halloy SendKeys.

## Phases

### P0 — Detached listen
Start-TalkSeat / Start-IrcTsr start listen via Start-Process (or equivalent) so parent shell exit does not kill it. Redirect stdout to listen.stdout.log when possible.

Exit: test or documented script path proves listen pid lives after starter returns.

### P1 — No home steal
Second Start-TalkSeat same home different nick errors and does not Stop-Process the live agent/listen.

Exit: test or dry-run assertion.

### P2 — PR
Open PR. Never push main. Never merge. composer-2.5 or build0.1 or grok-4.5. Never Other Models. Bob chairs MRB on #90.

## Kickoff

Read docs/feature-request-talk-seat-survival-2026-09-22.md and this plan. Implement P0-P1 for issue 90. Open a PR. Do not set an API key environment variable. Do not stamp UAT.
