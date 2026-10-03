<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/build-and-test-plan-bobs-must-bobiverse-webhook-delta-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: bobs !bobiverse pull + webhook delta (#129)

**Date:** 2026-09-22  
**Repo:** SimonBarnett/agentic_irc  
**FR:** `docs/feature-request-bobs-must-bobiverse-webhook-delta-2026-09-22.md`  
**Issue:** https://github.com/SimonBarnett/agentic_irc/issues/129  

## Goals

1. Periodic `!bobiverse` from fleet `bob-*` `irc_agent` (not chair, not talk seats, not `w-*`).
2. Reassemble chair `BOB DIGEST v1` whispers; ingest JSON into local `digest.json` + `bob-peers/`.
3. When local `bob-peers/<machine>.json` differs from chair row (excluding `lastSeen`), POST change-only merge via `post_working_on.post`.
4. Offline pytest; no live Ergo in CI.

## Non-goals

- agentic_build `Write-BobIrcStatus` producer (#196).
- UAT stamp.
- `password=` / `XAI_API_KEY=` in git.

## Phases

### P0 — Gates + assembler

- `should_periodic_bobiverse_pull` / talk-seat refusal.
- `DigestWhisperAssembler` for chunked JSON.

### P1 — Converge

- `merge_payload_local_peer_ahead_of_chair`
- `ingest_fleet_digest_pull`
- `irc_agent` pull loop + whisper handler.

### P2 — Tests + docs

- `tests/test_bobiverse_pull.py`
- FR + this plan committed.

## Definition of done

- [ ] `pytest -q` green offline
- [ ] PR from work branch; title includes `#129`
- [ ] Never push `main`; never merge; no UAT stamp in PR body
