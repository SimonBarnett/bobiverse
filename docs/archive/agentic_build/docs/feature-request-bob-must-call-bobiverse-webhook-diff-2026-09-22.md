<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-bob-must-call-bobiverse-webhook-diff-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: bob-* must call `!bobiverse`; webhook only on local diff

**Date:** 2026-09-22  
**Repo:** https://github.com/SimonBarnett/agentic_build  
**GitHub issue:** https://github.com/SimonBarnett/agentic_build/issues/196  
**Sister (change-only POST):** https://github.com/SimonBarnett/agentic_build/issues/141  
**Consumer:** agentic_irc #73 / PR #79 on main  
**Raised by:** Simon on `#bobiverse`  
**UAT + hostile MRB owner:** Bob  

## Problem

Simon: the bobs are not calling `!bobiverse`. When they call it, if
their local data is different, they send it via the webhook.

Today `bob-*` Watch may stay silent on the chair command. Digest /
systray then starve or show stale peers. Talk seats must still never
send `!bobiverse`.

## Gap vs current tree

#141 locks change-only POST from `Write-BobIrcStatus` (skip
`lastSeen`-only). It does not lock that **`bob-<machine>` must actually
issue `!bobiverse`** so the chair answers and the box can compare
local vs chair/digest and POST a delta.

FAIL #156 is a prior producer SHA. This FR is the call + compare
gate, not a second consumer.

## LOCKED

1. Each `bob-<machine>` calls `!bobiverse` on a cadence (interval
   UNKNOWN until measured; must be frequent enough that peers are not
   stale).
2. After the chair answer, if **local** Cursor / xAI / jobs /
   `working_on` / online differs from what the chair/digest has (or
   from last successful POST), POST the webhook. Same change-only
   rule as #141: `lastSeen`-only is not a POST.
3. Talk seats (`{machine}-{seatPid}`) never send `!bobiverse`.
4. Do not stamp UAT from workers.

## UNKNOWN

1. Cadence (seconds / minutes).
2. Exact compare fields vs #141 payload (must not invent secrets).
3. Whether a silent chair (no whisper) retries or logs only.

## Acceptance

1. Live `bob-ionos` / `bob-marchhare` / `bob-flamingo` / `bob-dev1`
   each emit `!bobiverse` without a talk seat doing it.
2. Duplicate local state after a call does not POST.
3. Changed fuel / jobs / online POSTs once (204) then duplicate is
   no-op (200 / `changed=False`).
4. No UAT stamp on the implementing PR.

## Out of scope

- Talk-seat nicks in Halloy (agentic_irc #128).
- agentic_build #175 two persistent workers (23624 FIX).
