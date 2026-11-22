---
name: bobiverse-jeeves-agent-harvest
description: >
  Honesty-box harvest loop for the Jeeves agent: after each finding or
  session, harvest reusable lessons back to the Jeeves skill book in
  SimonBarnett/bobiverse via Invoke-BobiverseHarvest.ps1, reusable lessons
  only, no plan content or secrets. Use at session end, after a finding, or
  /bobiverse-jeeves-agent-harvest.
depends_on: []
---

# bobiverse-jeeves-agent-harvest

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. File every issue / FR / bug / gap you find in the SAME turn via the intake webhook (`https://bob.ntsa.uk/bob/v1/intake`):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
> 2. Before finishing, run `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "..." -Lesson "..."` then `-Flush`.
> 3. Never put a token, password, SASL/NickServ secret, oper credential, key or private hostname in a filing, a skill, IRC or a log.

Long form: shared `harvest` skill book. This node is the short loop for the Jeeves agent.

## Honesty box

Using a skill book obliges you to give back: a lesson, an issue or an FR to the repo that owns the book.
The Jeeves agent's book is `jeeves/.grok/skills/` in `SimonBarnett/bobiverse`.

## Loop

1. After every finding and at session end:
   `.\scripts\Invoke-BobiverseHarvest.ps1 -Repo SimonBarnett/bobiverse -Summary "what broke / what fixed it" -Lesson "one reusable playbook line"`
2. Then `.\scripts\Invoke-BobiverseHarvest.ps1 -Flush` to resend anything queued offline.
3. A lesson for a specific skill names it (e.g. `bobiverse-jeeves-agent-queue-triage`) so the promote PR lands in
   the right book.

## What qualifies

- Reusable, generic, true next time: a check, a cause -> fix mapping, a stop rule.
- Not: one-off status, plan content / product decisions, timestamps-only notes, anything secret,
  private hostnames or IPs.

## Stop rules

Do not keep private notes instead of harvesting. Do not harvest the same lesson twice; twin-check first.
