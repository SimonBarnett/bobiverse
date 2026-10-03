<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-bobs-must-bobiverse-webhook-delta-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: bobs must !bobiverse; POST webhook when local digest differs

**Date:** 2026-09-22  
**Repo:** https://github.com/SimonBarnett/agentic_irc  
**GitHub issue:** https://github.com/SimonBarnett/agentic_irc/issues/129  
**Raised:** Simon IRC 2026-09-22  
**UAT + hostile MRB owner:** Bob  

## Problem

Fleet `bob-*` agents are not calling `!bobiverse`. When they do call it, if the chair digest differs from that bob's **local** peer/tray data, the bob should **POST the delta via the digest webhook** (change-only), so the shared digest converges.

## Gap vs current tree

- Digest chair / change-only webhook already exists (#73 closed).
- Systray consuming digest: #81 (producer shape).
- This FR is the **call + converge** loop: invoke `!bobiverse`, then webhook when local differs.
- Sister producer: https://github.com/SimonBarnett/agentic_build/issues/196 (Watch webhook POST). Talk seats never send `!bobiverse`.

## LOCKED

1. Fleet `bob-*` agents MUST call `!bobiverse` (digest pull) as part of normal Watch / status refresh (~120s).
2. When a bob's local peer/tray data differs from the chair digest, that bob MUST POST the delta via the digest webhook (change-only; no `lastSeen`-only POST).
3. Talk seats MUST NOT send `!bobiverse`.
4. No UAT stamp.

## Non-goals

- Replacing the #130 `cursor_pools` Spending-group wire.
- Implementing agentic_build Watch webhook (sister #196).
- Stamping UAT.

## Acceptance

1. `bob-*` `irc_agent` sends `!bobiverse` on `#bobiverse` on the agent tray cooldown.
2. Chair digest whisper is ingested locally (digest + bob-peers) and local-ahead fields POST to `/bob/v1/report`.
3. Offline pytest covers pull gate, assembler, merge payload, and whisper handler.
4. Bob chairs hostile MRB on issue #129.
