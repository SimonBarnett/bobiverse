<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/evidence/issue-128-offline-nick-drop-notes.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Issue #128 — offline nick drop (P0 measure + P1)

**Date:** 2026-09-22  
**Ergo:** `irc.ntsa.uk` ergo-2.19.1 (bobiverse)

## Symptom

Talk-seat nicks (`flamingo-<seatPid>`, etc.) stayed in Ergo `#bobiverse` NAMES
after the seat stopped answering. Halloy user lists matched Ergo NAMES, so
offline flamingos looked present.

## LOCKED bound (UNKNOWN 2 → measured)

| Case | NAMES drop time (live measure) | Acceptance bound |
|------|-------------------------------|------------------|
| Abrupt TCP close (no QUIT, client RST) | **≤10 s** (`deadtcp-*` probe 2026-09-22) | — |
| Half-open / box-off (no client RST; stop PONG) | Live `halfopen-*` stall **15 s** on 2026-09-22; Ergo `idle-timeouts` worst-case **240 s** | **240 s** acceptance cap |

**LOCKED 1 / Acceptance 1:** offline talk-seat nicks must leave `#bobiverse`,
shop, and `#agentic_irc` NAMES within **240 seconds** (Ergo worst-case). Client
paths below aim to clear sooner.

Live probe logs (redacted): `docs/evidence/ergo-dead-tcp-measure.log`,
`docs/evidence/ergo-half-open-measure.log`, `docs/evidence/issue-140-bobiverse-names-redacted.log`

## Mechanisms (P1)

| Case | Fix |
|------|-----|
| Coordinator PowerShell (`seat=`) exits; `irc_agent` still up | `seat_liveness_loop` → `QUIT` when coordinator PID gone (`AGENTIC_IRC_SEAT_LIVENESS_S`, default 15s) |
| `Start-TalkSeat` recycle / kill agent | `agent_control.py` writes `agent.quit.request`; agent `QUIT`s before `Stop-Process -Force` |
| Home has no `irc_agent` (crash/kill); nick may ghost | `bob-*` fleet agent `talk_seat_ghost.maybe_prune_local_ghosts` → brief `ghost_quit_session` |
| Deaf / hung seat (coordinator alive, no server lines / PONG overdue) | `seat_recv_idle_s` (default 150s) or `pong_grace_s` (default 45s) → `QUIT` |
| Box-off / half-open TCP only | Ergo server bound **240s**; Halloy matches within that window |

Live seats that still receive server traffic and answer `PING` with `PONG` are
unchanged.

## Evidence notes (no contradict LOCKED 1)

- Coordinator-gone QUIT loop: `tests/test_offline_nick_liveness.py`
- Graceful stop + ghost prune + idle/PONG: same pack + `tests/test_agent_control.py`, `tests/test_talk_seat_ghost.py`
- A live `flamingo-*` seat that still PONGs is not dropped by coordinator PID polling (only when PID is gone or recv/PONG paths fire).
