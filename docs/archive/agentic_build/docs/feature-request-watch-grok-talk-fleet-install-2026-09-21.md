<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-watch-grok-talk-fleet-install-2026-09-21.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: Install Watch-GrokTalk on fleet boxes (Watch-Bobiverse stays dumb)

**Date:** 2026-09-21
**Repo:** https://github.com/SimonBarnett/agentic_build
**Sister:** https://github.com/SimonBarnett/agentic_build/issues/126
`docs/feature-request-bob-grok-irc-listen-talk-worker-2026-09-21.md`
**Raised by:** Hostile MRB of SHA `5bac781ee62236db761ca8489832a07d815175fc` (PR #127 / issue #126)
**UAT + hostile MRB owner:** Bob

## Problem

#126 landed `Invoke-BobGrokTalkTick` and `tools/Watch-GrokTalk.ps1`.
`Install-BobFleet` still only registers `_Watch-BobJobs-<id>` and
`_Watch-Bobiverse-<id>`. Nothing starts the grok-talk poller. Inbox lines
sit unread unless an operator runs `Watch-GrokTalk.ps1` by hand. Addressed
English on `#bobiverse` still stops at the canned ACK.

This is not a #126 MUST (AC1–AC4 do not require a scheduled task). Do not
implement on the #126 FIX job. Watch-Bobiverse stays **no grok.exe**.

## LOCKED

1. Register a per-machine scheduled task (same AtLogOn + demand-start
   pattern as `_Watch-Bobiverse-<id>`) that runs `tools/Watch-GrokTalk.ps1`.
2. Do **not** call `Invoke-BobGrokTalkTick` / start grok.exe from
   `Watch-Bobiverse.ps1`.
3. Max concurrent grok-talk jobs per machine stays **1** (issue #126).
4. Off-DEV Test-Pack. No live Ergo. No live grok in CI. PR only.
5. No `password=` / API-key assignments in git.

## UNKNOWN

- Wrapper script vs direct `Watch-GrokTalk.ps1` (Bobiverse uses
  `_Watch-Bobiverse-<id>`).
- Poll interval (script default is 15s).

## Gap vs tree (at 5bac781 / PR #127)

| Current | Wanted |
|---|---|
| `Watch-GrokTalk.ps1` exists | `Install-BobFleet` registers and starts it |
| Watch-Bobiverse stays dumb | Stay dumb — do not fold the poller in |
| Operator must start the poller by hand | Task at logon, one per machine |

## Acceptance

- **AC1** `Install-BobFleet` registers `_Watch-GrokTalk-<machineId>` (or
  documented equivalent) pointing at `tools/Watch-GrokTalk.ps1`.
- **AC2** Watch-Bobiverse source still has no `Invoke-BobGrokTalkTick`,
  `grok-inbox`, or grok.exe start.
- **AC3** Test-Pack asserts the install wiring. No live Ergo. No secret
  assignments.

## Non-goals

- Changing the #126 consumer / envelope / fuel gate (those stay on #126).
- LLM inside Watch-Bobiverse.
- MRB PDF. UAT stamp.
