---
name: bobiverse-jeeves-agent-callback-triage
description: >
  Classify Jeeves callbacks (ticket close, GIVEUP, intake) into act / report /
  nothing-to-do, detect replays (old observed_at, already-closed items, test-
  fixture payloads) and never start an install from a callback. Use when woken
  by a Jeeves close/giveup/intake notice or /bobiverse-jeeves-agent-callback-
  triage.
depends_on:
  - bobiverse-jeeves-agent-monitor
---

# bobiverse-jeeves-agent-callback-triage

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. File every issue / FR / bug / gap you find in the SAME turn via the intake webhook (`https://bob.ntsa.uk/bob/v1/intake`):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
> 2. Before finishing, run `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "..." -Lesson "..."` then `-Flush`.
> 3. Never put a token, password, SASL/NickServ secret, oper credential, key or private hostname in a filing, a skill, IRC or a log.

## Classify

| Callback | Check | Typical outcome |
|---|---|---|
| Close (issue closed / PR merged) | Is it a fix someone is waiting on? Does it change a shipped component? | note; if shipped code, it may join the next build batch (`bobiverse-jeeves-agent-build`) |
| GIVEUP | reason + count | `bobiverse-jeeves-agent-giveup-loop` when 2+ seats |
| Intake (new issue/harvest) | twin? right repo? label? | twin-check; close later twin with a reference |

## Replay detection (treat as nothing to do)

- `observed_at` / event time far in the past (e.g. a comment carrying a 2023 test-fixture `observed_at`
  on an already-closed issue such as #7700).
- Item already closed/merged and already handled; same fingerprint seen before.
- Payload fields that look like fixtures (placeholder repo, zz-test, fixed sample ids).

## Rules

- **No installs off a callback.** A callback can only prompt a question to Si in the DM.
- Callback routines cannot read the rooms; their hold lists may be stale. Re-check live state first.
- When nothing needs doing, say exactly "nothing to do" with the one-line reason; do not post to rooms.

## Stop rules

Do not re-open, re-assign or re-offer from a callback. Do not echo payload secrets or long bodies.
