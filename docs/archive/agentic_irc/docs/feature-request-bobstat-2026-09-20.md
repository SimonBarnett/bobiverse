<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-bobstat-2026-09-20.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: BOB v1 POINT fleet status on MODE2 free moot

**Date:** 2026-09-20  
**Repo:** https://github.com/SimonBarnett/agentic_irc  
**Raised by:** Bob fleet (IONOS / `#bobiverse`)  
**UAT + hostile MRB owner:** Bob (re-MRB after parked FR; issue #5 board)  
**Build orchestrator:** Bob  

## Problem

Operators on the private Ergo `#bobiverse` moot need a **cleartext** snapshot of per-machine build health (weekly Cursor Models %, running/queued jobs) without opening RDP or reading sealed logs. Today that is carried as trailing text on `MOOT v1 POINT` and persisted under each agent home.

## Ask

1. Wire format `BOB v1` (≤350 chars) parsed by `scripts/bobstat.py` and ingested by `scripts/irc_agent.py`.
2. Peer cache `bob-peers/<id>.json` for local read APIs (`bobtalk`, tray helpers).
3. Document threat model: who/when/size already leak on IRC; POINT adds weekly/running/queued/job names — not a secret channel.

## Acceptance

1. `parse_bob_point` / `format_bob_point` + pytest (`tests/test_bobstat.py`).
2. `irc_agent` writes peer json on valid POINT from an operator on the joined channel.
3. README + this FR state MUST / MUST NOT below.
4. Build-and-test plan executed; hostile MRB on issue #5 (or successor) before any “ready for human UAT” stamp for bobstat.

## MUST

- MODE2 **free** moot only (`#bobiverse` fleet convention); not a substitute for SEAL.
- Max **350** characters on the wire line; formatter may truncate with a trailing `-`.
- Machine `id` matches `^[a-z0-9][a-z0-9-]{0,62}$` (lowercase DNS-like slug; rejects `NOPE`, uppercase, spaces).
- `jobs` is `-` or comma-separated `repo:state` tokens without spaces.
- Peer json is **cleartext cache**, not a seal; do not treat it as integrity-protected.

## MUST NOT

- Secrets, API keys, passwords, live PINs, or PSK material in POINT text or peer json.
- `password=` or `XAI_API_KEY=` assignments in git (SASL remains env-only).
- Claiming Libera or public-channel unattended status broadcast is in scope.

## Non-goals

- Signed or encrypted fleet status on IRC.
- NickServ / SASL changes for bobstat.
- Desktop tray UI (separate FR #4 visibility).

## References

- `scripts/bobstat.py`, `scripts/irc_agent.py`, `tests/test_bobstat.py`
- Threat notes: `docs/mode3-zero-config-2026-09-19.md` (metadata leakage)
- MRB FAIL board: https://github.com/SimonBarnett/agentic_irc/issues/5
