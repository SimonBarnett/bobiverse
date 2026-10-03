<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-visible-nicks-umode-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: clear Ergo +i so Halloy WHO shows talk-seat nicks

**Date:** 2026-09-22
**Repo:** https://github.com/SimonBarnett/agentic_irc
**GitHub issue:** https://github.com/SimonBarnett/agentic_irc/issues/110
**Raised by:** Simon (Halloy user list empty; Ergo LUSERS 0 visible / all invisible)
**UAT + hostile MRB owner:** Bob
**Build orchestrator:** Bob
**Implementation SHA (PR #106):** `6ea13b4186b1d05c6489dd8a2a868f95becc137d`

No source PDF was supplied. This park is after the code PR existed.

## Problem

Ergo `default-user-mode` is `+i`. Server LUSERS reports **0 visible** and
every talk seat as invisible. Halloy nick lists that populate from WHO then
omit flamingos (`flamingo-<pid>`) even when those nicks are already in the
channel.

## Ask

After registration (001), `scripts/irc_agent.py` must clear invisible on the
live nick **before JOIN**, so a recycled talk seat is visible to WHO / Halloy.

## LOCKED

1. After `ready` (001), before `JOIN`: send `MODE <live_nick> -i`.
2. Use `live_nick` (post-433 collision suffix), not a hardcoded original nick.
3. Offline pytest locks the MODE send. CI must not open Ergo.
4. No `password=` / `XAI_API_KEY=` assignments in git.
5. Do not stamp UAT. Live Halloy recycle (`/names` / WHO shows
   `flamingo-17568` and `flamingo-24108`) is Bob.

## MUST NOT

- Change Ergo server `default-user-mode` (client-side only).
- Recycle already-connected seats from this FR (operator).
- Clear `+i` on Mode 3 `dumb_agent` / thin (out of scope; talk seats only).

## Gap vs tree before PR #106

| Item | Status |
|---|---|
| `Client.session` MODE `-i` after 001 | **Missing** on `main` @ `d71aae3` |
| Source needle in `tests/test_agent.py` | **Missing** |
| This FR + plan | **This park** |

## Acceptance (issue #110)

1. This markdown + issue #110 exist (intake).
2. `irc_agent.Client.session` sends `MODE <live_nick> -i` after 001 and before JOIN.
3. Offline pytest asserts that send. Full `pytest -q` stays green.
4. No secrets in the product diff.

## Non-goals

- Mode 3 DUMB / `dumb_agent.py` umode.
- Server-side Ergo config.
- Declaring UAT for live Halloy.

## Related

- Plan: `docs/build-and-test-plan-visible-nicks-umode-2026-09-22.md`
- PR: https://github.com/SimonBarnett/agentic_irc/pull/106
- Talk-seat survival (different FR): `docs/feature-request-talk-seat-survival-2026-09-22.md`
