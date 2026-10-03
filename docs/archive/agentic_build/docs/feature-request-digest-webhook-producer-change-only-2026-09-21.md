<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-digest-webhook-producer-change-only-2026-09-21.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: change-only webhook POST from `Write-BobIrcStatus`

**Date:** 2026-09-21  
**Repo:** https://github.com/SimonBarnett/agentic_build  
**GitHub issue:** https://github.com/SimonBarnett/agentic_build/issues/141  
**Sister (consumer):** https://github.com/SimonBarnett/agentic_irc/issues/73  
`docs/feature-request-digest-webhook-chair-change-only-2026-09-21.md`  
**Related:** #124 shop + write-only `reportUrl` (join/POST contract, not this delta gate)  
**Raised by:** Simon (parked from agentic_irc MRB of a0102b350157649d2d5673e71687058808e9e705)  
**UAT + hostile MRB owner:** Bob  

## Problem

`Write-BobIrcStatus` refreshes local `bob-peers\<id>.json` and may still emit
change-talk English to the IRC outbox. It does **not** POST a fleet digest
to ionos `reportUrl`. Chair `digest.json` therefore starves unless someone
still talks on `#bobiverse`.

Sister #73 locked a **change-only** write: peers POST when real state
changes (fuel, jobs, online, `working_on`, repo/sha/model). A `lastSeen`-only
tick must not POST. Periodic English / `BOB DIGEST` / POINT on `#bobiverse`
is not this producer’s job.

## LOCKED

1. **POST on delta only.** Before POST, diff vs last successful POST (or last
   exported `bob-peers\<id>.json`). Skip when only `lastSeen` advanced.
2. **Payload fields** when present: `online`, `status`, `weekly` /
   `cursor_label`, `jobs`, `working_on`, `repo` / `sha` / `model` / `fuel`.
   No secret-shaped JSON fields. Header `X-Bob-Secret` only (file/env, never
   git).
3. **`config/bobiverse.json`** gains `chairNick` / `chairHome` / `reportUrl`
   as needed for the producer. Watch does **not** start the digest chair.
4. **`Install-BobChair`** (one-shot) may live in this repo if the consumer
   chair seat is launched from here. Do not make `Watch-Bobiverse` the chair.
5. No periodic English / `BOB DIGEST` / POINT on `#bobiverse` from this path.
6. No `password=` / `XAI_API_KEY=` assignments in git.

## Gap vs current tree

| Current | Wanted |
|---|---|
| `Write-BobIrcStatus` writes disk peer + optional change-talk | Same, plus change-only POST to ionos `reportUrl` |
| `bobiverse.json` has nicks/host only | Add `chairNick` / `chairHome` / `reportUrl` |
| No webhook client | Hermetic Test-Pack: delta POSTs; lastSeen-only does not |

## Acceptance

1. Fixture: fuel or job change → one POST. lastSeen-only tick → zero POST.
2. Watch still does not become the chair. No channel DIGEST/POINT from this path.
3. Test-Pack hermetic (fake HTTP). PR only; Bob stamps UAT.

## Non-goals

- Implementing agentic_irc chair / webhook server (#73 consumer).
- Shop JOIN / `w-<short>-<pid>` attach (#124).
- HTTP GET digest. TipForm layout (#142 / #91).
