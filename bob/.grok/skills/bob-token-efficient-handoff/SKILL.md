---
name: Bob token-efficient handoff
description: >-
  Use when dispatching Bob Fleet FR/MRB/UAT work, picking workers from live
  fuel, mandatory !bored after 2m idle for Cursor/Grok/Aider, or Sand-empty
  deterministic claim.
---
# Token-efficient Bob dispatch

## Bob’s own tokens
Bob listens on `#bobiverse` (Jeeves GIT announces) and may start/assign seats while Sand lasts. Do not burn chat tokens on FR/MRB/UAT implementation — workers do the work.

## Three modes (only)
| Mode | What | Settings |
|------|------|----------|
| **FR** | Earliest unclosed issue/FR → open PR | low (code) |
| **MRB** | Hostile review of a PR | medium |
| **UAT** | After MRB PASS — **separate worker process** | high; **only Bob stamps UAT** |

## CAST IRON — Jeeves + idle workers
- Jeeves announces GIT work **to bobs on `#bobiverse` only**.
- Unaccepted queue lives on the digest webhook.
- **Every** worker process (Cursor, Grok, Aider, free) with **no work > 2 minutes MUST `!bored`**.
- **Jeeves never offers.** The **bob-{machine} ear** offers the top unaccepted job **addressed to that nick** in `#{machine}` and takes the ACK.
- Jeeves sits silently in `#{machine}`: on worker **ACK** it fires the webhook (accepted + busy + activity `<MODE> <repo>#<n> <title>`); on **DONE** it marks completed, clears activity, sets idle and applies supersede.

## Worker choice
- Prefer a **different** worker for MRB than the PR author **only when 2+ workers are available**.
- One seat free → that seat may continue into MRB.
- MRB **PASS** → merge + close source issue/FR → Jeeves announces → **separate UAT worker**.
- MRB **FAIL** → one fix PR, merge both, issue stays open (no UAT).

## Sand empty
Fully deterministic: webhook queue + mandatory `!bored` + ear's addressed offer + ACK/DONE recorded by Jeeves. No Bob LLM required.

## Fuel first
Read `https://irc.ntsa.uk/bob/v1/report` before paid seats. Prefer free when Sand is thin. Copilot only when CCA is live.

Seat agent order is **Grok first, then Cursor** (FR #3997). Grok tokens refresh weekly and Cursor tokens monthly. Start or restart seats on this machine's weekly Grok while its fuel is > 0. Switch to Cursor only when that machine's Grok is really exhausted (402 `usage balance exhausted`, `creditUsagePercent` 100, out-of-tokens dialog) and Cursor has fuel. An unknown or failed fuel read is not exhausted (#3923). The choice is made only at start/restart, never mid-job. After the weekly Grok reset, the next start goes back to Grok.

## Harvest
This `!bored` rule must land in **Cursor and Grok** worker packs / AgentMonitor as well as Aider. Honesty-box → agentic_build.

## Related
[Bob MRB worker](sand-workflow:bob-mrb-worker) · [Bob GIT ACCEPT claim](sand-workflow:bob-git-accept-claim) · [Bob worker activity webhook](sand-workflow:bob-worker-activity-webhook)
