<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-bobs-call-bobiverse-webhook-delta-2026-09-22.md, last changed 2026-09-24. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: bobs must `!bobiverse`; POST webhook when local digest differs

**Date:** 2026-09-22  
**Repo:** SimonBarnett/agentic_irc  
**GitHub issue:** https://github.com/SimonBarnett/agentic_irc/issues/129  
**Raised by:** Simon on IRC 2026-09-22  
**UAT + hostile MRB owner:** Bob  

## Problem

Simon: **the bobs are not calling `!bobiverse`.** When they do call it, if
their local data is different, they should send the delta via the digest
webhook.

Fleet `bob-*` agents should pull the chair digest as part of normal Watch /
status refresh. They currently do not. When a bob does pull, if the chair
digest differs from that bob's **local** peer/tray data, the bob should
**POST the delta** on the change-only digest webhook so the shared digest
converges.

## Gap vs current tree

- Chair answers `!bobiverse` whisper JSON (`BOB DIGEST v1 i/n`) — #81 wire.
- Sister Watch enqueue of channel `!bobiverse` is off unless
  `BOB_IRC_ENQUEUE_BOBIVERSE_PULL=1`.
- Change-only webhook exists (#73 closed). Bobs do not POST a local-vs-chair
  delta after a pull.

## LOCKED

1. Fleet `bob-*` agents call `!bobiverse` on their normal refresh path
   (Watch / status), not only when a human types it.
2. After a pull, if local peer/tray data differs from the chair digest, the
   bob POSTs the delta via the existing digest webhook (change-only).
3. Whisper-only chair answer. No channel JSON dump. No POINT firehose.
4. No secrets on the wire (`password=` / report.secret / API key literals).
5. Do not stamp UAT from workers. Bob owns UAT.

## Related

- Digest chair / change-only webhook: agentic_irc #73 (closed).
- Systray consuming digest: agentic_irc #81.
- Sister ingest: SimonBarnett/agentic_build.

## Acceptance

1. A live `bob-*` Watch/status cycle issues `!bobiverse` without a human
   typing it.
2. When local peer/tray fields differ from the chair digest, the bob POSTs
   a change-only webhook payload (no secret leak).
3. Offline pytest; no live Ergo in pack.
4. PR only; Bob stamps UAT.

## Non-goals

- Gutting #81 digest shape.
- Reintroducing channel POINT / `BOB DIGEST` on `#bobiverse`.
- HTTP GET of digest.
