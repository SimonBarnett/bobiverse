<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-talk-seats-back-bobiverse-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: talk seats rejoin `#bobiverse`

**Date:** 2026-09-22  
**Repo:** https://github.com/SimonBarnett/agentic_irc  
**GitHub:** https://github.com/SimonBarnett/agentic_irc/issues/108  
**MRB:** https://github.com/SimonBarnett/agentic_irc/issues/109  
**Raised by:** Simon (Halloy) - everyone move back to `#bobiverse`  
**UAT owner:** Bob  
**Supersedes:** #98 / #100 LOCKED items that keep talk seats off `#bobiverse`

## Problem

#99 / PASS-nits #101 shipped `channels_for_nick` + `Start-TalkSeat` so
`{machine}-{pid}` talk seats JOIN shop + extras only. Simon then asked
everyone back onto `#bobiverse`. PR #107 (`f3f159816edcf8ef908d1e55f0a040833827bd86`)
flipped the code and inverted the tests with **no** parked FR, **no** plan,
and **no** skill/`/docs` update. Closed #98 / #100 still lock the opposite.

## Gap vs current tree (`main` @ `d71aae3`)

| Area | Now (after #99) | Want |
|------|-----------------|------|
| `channels_for_nick` talk seat | shop + extras; strips `#bobiverse` | `#bobiverse` + shop + extras |
| `Start-TalkSeat.ps1` default | `#{mid},#agentic_irc` | `#bobiverse,#{mid},#agentic_irc` |
| `w-*` | shop only | shop only (unchanged; #46 / #70) |
| `bob-*` | fleet + shop | unchanged |
| Jeeves | fleet + every shop | unchanged |
| `docs/feature-request-*-bobs-only*` / `*-shop-auto*` | LOCKED: talk seats not in `#bobiverse` | mark superseded; do not leave both laws live |
| `.grok/skills/agentic-irc/SKILL.md` | JOIN **shop only** (not `#bobiverse`) | talk seats JOIN fleet + shop + extras |

No source PDF was supplied.

## LOCKED

1. `{machine}-{pid}` talk seats JOIN `#bobiverse` + `#{machine}` + extras (`#agentic_irc`, `#airc-moot`). `channels_for_nick` MUST NOT strip fleet for those nicks.
2. `Start-TalkSeat.ps1` with no `-Channel` defaults to `#bobiverse,#$mid,#agentic_irc`.
3. `w-*` stay shop only. Do not put workers on `#bobiverse`.
4. `bob-*` stay `#bobiverse` + `#{machine}`. Jeeves stays `#bobiverse` + every shop.
5. `/docs` and `agentic-irc` rooms table match LOCKED 1-4. Closed #98 / #100 docs state they are superseded for talk-seat fleet membership.
6. Recycle is local (same as #100 non-goal): no auto-PART of already-connected remote seats.

## UNKNOWN

- Whether Simon's "everyone" includes anything other than talk seats. Workers stay shop-only until a later FR.

## Acceptance

| ID | Gate |
|----|------|
| TS1 | `channels_for_nick("flamingo-17568", "#bobiverse,#flamingo")` -> `#bobiverse`, `#flamingo` |
| TS2 | `channels_for_nick("ce-priority-dev1-16948", "#bobiverse,#ce-priority-dev1,#agentic_irc")` -> fleet + shop + `#agentic_irc` |
| TS3 | `channels_for_nick("w-fl-4412", "#bobiverse")` -> `#flamingo` only |
| TS4 | `Start-TalkSeat` default channel string includes `#bobiverse` |
| TS5 | Parked #98 / #100 markdown + `agentic-irc` skill no longer teach shop-only talk seats |

## Non-goals

- Mode 3 pairing on `#bobiverse` (still forbidden).
- Worker JOIN `#bobiverse`.
- ChanServ; digest / `!bobiverse` contract; UAT stamp.
