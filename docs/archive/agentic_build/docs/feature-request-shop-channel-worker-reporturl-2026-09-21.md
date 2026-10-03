<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-shop-channel-worker-reporturl-2026-09-21.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: shop channels + worker attach + write-only `reportUrl`

**Date:** 2026-09-21  
**Repo:** https://github.com/SimonBarnett/agentic_build  
**GitHub issue:** https://github.com/SimonBarnett/agentic_build/issues/124  
**Sister (protocol):** https://github.com/SimonBarnett/agentic_irc/issues/46  
`docs/feature-request-shop-channel-worker-cc-webhook-2026-09-21.md`  
**Related:** #141 change-only POST gate (delta contract, not shop JOIN)  
**Raised by:** Simon  
**UAT + hostile MRB owner:** Bob  

## Problem

`Watch-Bobiverse` JOINs `#bobiverse` only. MRB/build workers have no shop
nick. There is no `reportUrl` in `config/bobiverse.json` and no write-only
POST client. Sister shop FR needs this producer: Watch in `#bobiverse` **and**
`#<machine>`; workers JOIN `#<machine>` as `w-<short>-<pid>`; POST
`reportUrl` write-only. `!report` stays scrubbed. `!bobiverse` is IRC read
only.

## LOCKED

1. **Ids** stay `flamingo`, `marchhare`, `ionos`, `ce-priority-dev1`.
   Shop channel is `#<machine>` (`#dev1` = `#ce-priority-dev1`).
2. **`bob-*` Watch** JOINs `#bobiverse` and the local shop. Workers JOIN the
   shop only — never `#bobiverse`. Nick `w-<short>-<pid>`
   (`io` / `fl` / `mh` / `d1`).
3. **Write-only `reportUrl`** in `config/bobiverse.json`. POST merge /
   delete-worker / shop-down. Secret is header `X-Bob-Secret` (file/env),
   never a JSON field, never IRC, never git.
4. **No `!report` write path.** `!bobiverse` remains the IRC read.
5. **No HTTP GET** of digest. No traces on shop or `#bobiverse`.
6. No `password=` / `XAI_API_KEY=` assignments in git.

## Gap vs current tree

| Current | Wanted |
|---|---|
| Watch JOINs `#bobiverse` only | Also JOIN `#<machine>` shop |
| Workers have no IRC shop nick | `w-<short>-<pid>` on shop only |
| No `reportUrl` / POST client | Write-only callback on change (see also #141) |

## Acceptance

1. Hermetic: Watch fixture joins fleet + shop; worker fixture nick is shop-only.
2. POST helper exists; GET is not implemented.
3. Skills `bob-irc` / `bobiverse.md` match LOCKED. PR only; Bob stamps UAT.

## Non-goals

- Chair identity / change-only skip gate (#141).
- Tray ingest of `BOB DIGEST v1` (#142).
- Public digest URL. ChanServ. WinRM.
