<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/evidence/issue-140-offline-nick-fix-evidence.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Issue #140 — offline nick FIX evidence

**Date:** 2026-09-22  
**MRB:** https://github.com/SimonBarnett/agentic_irc/issues/140  
**FR:** `docs/feature-request-offline-nicks-stay-in-chat-users-2026-09-22.md`  
**Git SHA:** `0389651` (branch `work/e941dc92-fix-issue-140-offline-nicks`)

## UNKNOWN 2 → LOCKED

| Case | Measured NAMES drop | Acceptance |
|------|---------------------|------------|
| Abrupt TCP close (RST, no QUIT) | **10 s** (`deadtcp-*`, 2026-09-22) | within **240 s** |
| Half-open / no PONG (stall read) | **15 s** (`halfopen-*`, 2026-09-22) | within **240 s** |
| Worst-case Ergo idle-timeouts | 90s ping + 150s disconnect (server config) | **240 s** cap |

## P1 mechanisms (no “out of agent scope” carve-out for box-off)

- Coordinator gone → `seat_liveness_loop` QUIT (unchanged green path).
- Recycle/kill → `agent_control.graceful_stop_agent` (`agent.quit.request`, ACL on protected homes) before `Stop-Process` in `Start-TalkSeat.ps1`.
- Crash/kill with no agent → `bob-*` `talk_seat_ghost.maybe_prune_local_ghosts` (UNKNOWN 3 implemented).
- Deaf/hung → `seat_recv_idle_s` / `pong_grace_s` → QUIT.
- Box-off / half-open only → Ergo bound **240 s**; measured probes above are within bound.

## Live Ergo (redacted)

- Dead TCP: `docs/evidence/ergo-dead-tcp-measure.log`
- Half-open stall: `docs/evidence/ergo-half-open-measure.log`
- Live `flamingo-*` still in `#bobiverse` / shop / `#agentic_irc` while seats answer (Acceptance 2): `docs/evidence/issue-140-bobiverse-names-redacted.log`

Live Ergo probes on 2026-09-22 (this worker): `deadtcp-*` gone from `#bobiverse` NAMES in **10 s** after abrupt TCP close; `halfopen-*` (stop PONG, stall read) gone in **15 s**. Both within LOCKED **240 s**. Production `flamingo-*` kill/power-off is not re-run here; client QUIT / ghost-prune paths are covered by offline pytest.

## Tests

- `tests/test_offline_nick_liveness.py` — coordinator alive, dead PID, disable-env default, control QUIT, recv/PONG shutdown, `Start-TalkSeat` graceful stop wiring.
- `tests/test_talk_seat_ghost.py`, `tests/test_agent_control.py`

## UAT

No worker UAT stamp. Bob chairs MRB #140.
