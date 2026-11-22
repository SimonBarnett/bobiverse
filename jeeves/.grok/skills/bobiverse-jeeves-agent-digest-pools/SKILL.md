---
name: bobiverse-jeeves-agent-digest-pools
description: >
  Read fleet fuel pools and per-machine seat rows from the public digest (GET
  https://bob.ntsa.uk/bob/v1/report), flag stale or mislabelled rows (wrong
  kind/model, stale lastSeen, ghost jobs) and never compare it with the Grok
  Bot plan banner. Use for pool %, fuel, stale tiles, or /bobiverse-jeeves-
  agent-digest-pools.
depends_on:
  - bobiverse-jeeves-agent-monitor
---

# bobiverse-jeeves-agent-digest-pools

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. File every issue / FR / bug / gap you find in the SAME turn via the intake webhook (`https://bob.ntsa.uk/bob/v1/intake`):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
> 2. Before finishing, run `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "..." -Lesson "..."` then `-Flush`.
> 3. Never put a token, password, SASL/NickServ secret, oper credential, key or private hostname in a filing, a skill, IRC or a log.

## Read

`GET https://bob.ntsa.uk/bob/v1/report` (200 JSON). Key parts: pool list (remaining %, period end / reset),
`machines.<id>` (`online`, `lastSeen`, `pcent`, seats with `kind`, `model`, `jobs`, `running`, `queued`,
`working_on`).

## Flag

- **Stale row:** `lastSeen` old while the machine is online; `period_end` already past (pre-rollover data).
- **Mislabelled seat:** `kind` disagrees with the real agent (e.g. OpenCode reported as `grok`, or a literal
  `$model` placeholder - #7706 class).
- **Ghost jobs:** `running`/`queued` > 0 with empty `jobs`, or a job tile for a seat with no live process.
- **Missing pool:** a pool absent or `n/a` for a machine that has seats.

## Rules

- Report numbers exactly as the digest gives them, with the read time. Never invent or estimate a %.
- **Never compare digest pools with the Grok Bot plan/usage banner** - different accounts and meters.
- The digest `grok-weekly` pool is not a machine's own xAI weekly; read that on the machine.
- A remote host's local digest copy can lag; trust the public endpoint.

## Report

One block: pools (id, remaining %, reset), then per machine: seats, kind/model, idle/busy, flags.
Mislabel or stale publisher -> twin-check, then FR via `bobiverse-jeeves-agent-fr-filing`.
