---
name: bobiverse-jeeves-agent-channel-admin
description: >
  IRC channel administration for the fleet: !register / !unregister of
  #<machine> shops via ChanServ, roster checks, shop naming (registered
  #<machine>, else #wonderland; Windows 15-char name truncation), and op/half-
  op based authorisation (no operators list). Use for new machines, missing
  shops, ChanServ, or /bobiverse-jeeves-agent-channel-admin.
depends_on:
  - bobiverse-jeeves-agent-monitor
---

# bobiverse-jeeves-agent-channel-admin

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. File every issue / FR / bug / gap you find in the SAME turn via the intake webhook (`https://bob.ntsa.uk/bob/v1/intake`):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
> 2. Before finishing, run `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "..." -Lesson "..."` then `-Flush`.
> 3. Never put a token, password, SASL/NickServ secret, oper credential, key or private hostname in a filing, a skill, IRC or a log.

## Shop naming

- Shop = registered `#<machine>`, machine id = Windows computer name, lower-case.
- Windows computer names truncate at 15 characters, so the shop uses the truncated name
  (e.g. `#hrs-priority-de`).
- Unregistered machine: airc falls back to `#wonderland` (FR #3834 dropped the old domain/workgroup fallback).

## Commands (ops: +o/+h in #bobiverse)

- `!register <machine>` / `!unregister <machine>` (FR #4008 / #5161 / #5274): dry-run then confirm.
  `REGISTERED v1` only after ChanServ confirms. Core channels are refused.
  Unregister tombstones the shop so a lagging ChanServ LIST cannot re-add it.
- `!sweep [#chan]` re-plans +h/+o grants. `!resync` refreshes the roster from ChanServ.

## Authorisation

- Authority comes from live channel modes: +o / +h in `#bobiverse`. There is **no operators list**.
- Policy: `bob-<machine>` +o in its own shop, +h in `#bobiverse`, +o in `#wonderland`.
  Never op `*_console` or worker/seat nicks.

## Checks

Jeeves joined every registered channel (`channel-sync registered=<n> joined=<list>`), `op-in=` covers them,
and `registered-machines.json` matches the ChanServ LIST.

## Stop rules

Never edit `ircd.yaml` or restart `BobIrcd`. Never read or print ChanServ / NickServ / oper credentials.
Register/unregister only on Si's request.
