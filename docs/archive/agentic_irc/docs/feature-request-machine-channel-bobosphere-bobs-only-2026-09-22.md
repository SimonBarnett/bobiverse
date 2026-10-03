<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-machine-channel-bobosphere-bobs-only-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: per-machine channel for bob + talk seats (bobosphere = bobs only)

**Date:** 2026-09-22
**Repo:** https://github.com/SimonBarnett/agentic_irc
**GitHub:** https://github.com/SimonBarnett/agentic_irc/issues/100
**Raised by:** Simon on #agentic_irc
**UAT owner:** human

**Superseded (talk-seat fleet membership):** [issue #108](https://github.com/SimonBarnett/agentic_irc/issues/108) / [MRB #109](https://github.com/SimonBarnett/agentic_irc/issues/109) / `docs/feature-request-talk-seats-back-bobiverse-2026-09-22.md`. LOCKED items **3** (talk seats not in `#bobiverse`) and **5** (only bobs in `#bobiverse` — as applied to talk seats) no longer apply. LOCKED **4** (`w-*` shop only) and **6** (Jeeves in every shop) remain in force.

## Problem

Talk seats were in #bobiverse with builders. Bobosphere is for `bob-*` only (talk seats rejoin fleet per #108; see superseded note above).
Shop #{machine} holds bob + {machine}-* (+ workers). Jeeves is in every room.

## LOCKED

1. Create = first JOIN of #{machine-id}.
2. `bob-{machine}` → #bobiverse + #{machine}.
3. ~~{machine}-{pid} talk seats → #{machine} (+ extras); not #bobiverse.~~ **Superseded** by #108 / #109 (talk seats rejoin `#bobiverse` + shop + extras).
4. w-* → shop only.
5. Only bobs in #bobiverse.
6. Jeeves (irc_agent.py --chair) → #bobiverse + every #{machine}.

## Deliverable

channels_for_nick, parse_talk_seat_nick, chair_channels, Start-TalkSeat default, tests, skill.

## Non-goals

ChanServ; auto-PART remote seats (recycle locally); Mode 3 PIN chair on shops.
