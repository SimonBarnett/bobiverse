---
name: bobiverse-jeeves-agent-ergo-link
description: >
  Read-only check of Jeeves link to ErgoWalrus: channel-sync joined list vs
  registered machines, +o / op-in per channel, exact nick Jeeves, and NickServ
  identification status; recommend recovery, never restart Ergo. Use for missing
  joins, lost +o, nick fights, or /bobiverse-jeeves-agent-ergo-link.
depends_on:
  - bobiverse-jeeves-agent-monitor
---

# bobiverse-jeeves-agent-ergo-link

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. File every issue / FR / bug / gap you find in the SAME turn via the intake webhook (`https://bob.ntsa.uk/bob/v1/intake`):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
> 2. Before finishing, run `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "..." -Lesson "..."` then `-Flush`.
> 3. Never put a token, password, SASL/NickServ secret, oper credential, key or private hostname in a filing, a skill, IRC or a log.

Public hosts only: bob.ntsa.uk, irc.ntsa.uk, github.com.

Ergo on walrus is service `ErgoWalrus` (elsewhere `BobIrcd`). This skill reads
**Jeeves-side evidence** and may quote only listener/limits lines from Ergo config -
never SASL/NickServ/oper passwords or `oper.cred`. Never restart `ErgoWalrus`
(Si's OK every time). Never edit `ircd.yaml`.

## Checks

1. **Joins.** `logs\stdout.log` or `cmd-trace.log` recent
   `channel-sync registered=N joined=#bobiverse,#<machine>...` must list every
   registered machine channel plus `#bobiverse`.
2. **Ops.** `chair-status` / `op-in=` lists channels where Jeeves holds `+o`
   (need `#bobiverse` and each shop).
3. **Nick.** Exactly `Jeeves` (never `Jeeves_` / `Jeeves_l`; wrong-host or 433 must exit).
4. **NickServ.** Identification OK - no unverified WHOIS on the operator nick. Do not
   print account secrets; report only `identified=yes/no` style evidence from public
   status lines.

## Report

- joined channels vs registered machines (diff any missing)
- op state per channel
- nick + NickServ status
- evidence lines (redacted) and likely cause + existing-issue link when known
- **recommend** recovery (rejoin / `!resync` by ops / install ROLLBACK); do not perform restarts

## Likely causes (report, do not fix here)

| Symptom | Likely cause |
|---|---|
| Missing shop in joined= | channel-sync / registration lag; chair not past identify |
| Lost `+o` in `#bobiverse` | services/uptime race; needs ops |
| `Jeeves_` nick | 433 collision / wrong host (FR #6947 class) |
| Unverified nick | NickServ identify failed (cred path - escalate, never open `oper.cred`) |

## Stop rules

- Never restart `ErgoWalrus` or `ircJeeves` from this skill.
- Never read or print SASL/NickServ/oper passwords.

## Hard rules

- No secrets. Never print or open tokens, passwords, webhook keys, NSSM env values, `config\oper.cred`, `identity.json`, `_backup-nssm-env-*`, `inbound-transcript.log` or any passwords folder. Placeholders and paths only.
- Never edit the Jeeves ledger, `queue.json`, outbox or digest by hand.
- No `!assign`, no `!focus`, no fake `ACK` / `DONE` / `!bored` / `GIVEUP`, never `!build cancel`.
- Restarts of `ircJeeves`, seats or services only on Si's explicit OK. `ErgoWalrus` needs Si's OK every time. Never restart Jeeves while a build runs.
- One machine at a time, each with a backup and a ROLLBACK.