---
name: bobiverse-jeeves-agent-rollback
description: >
  Roll back a failed install: run the newest ROLLBACK.ps1 from the install's
  _hotpatch backup when post-checks fail, then re-run health, IRC +o and
  !resync checks and report. Use when an install post-check fails, Jeeves
  crash-loops after an upgrade, or /bobiverse-jeeves-agent-rollback.
depends_on:
  - bobiverse-jeeves-agent-install
---

# bobiverse-jeeves-agent-rollback

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. File every issue / FR / bug / gap you find in the SAME turn via the intake webhook (`https://bob.ntsa.uk/bob/v1/intake`):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
> 2. Before finishing, run `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "..." -Lesson "..."` then `-Flush`.
> 3. Never put a token, password, SASL/NickServ secret, oper credential, key or private hostname in a filing, a skill, IRC or a log.

Rollback is part of the install (Slab is the sole installer). Triggers are listed in
`bobiverse-jeeves-agent-install`.

## Steps

1. Find the newest backup for this install: `<ai root>\jeeves\_hotpatch_<yyyyMMdd-HHmmss>-jeeves-<sha8>\`
   (or the component's own backup folder). Confirm its `ROLLBACK.ps1` targets the build just installed.
2. Run that `ROLLBACK.ps1` elevated. It restores the previous files (and IIS config if backed up) and restarts
   only the affected service.
3. Post-check with `bobiverse-jeeves-agent-monitor`: hash == previous build's hash, service stable, Jeeves in
   `#bobiverse` with `+o`, `/bob/v1/report` 200 and fresh, queue intact, one `!resync` ok.
4. Report: machine, rolled back from -> to (SHA + hash), backup folder, time (operator zone), each post-check.
5. File the failure (what broke, log lines, build receipt) via `bobiverse-jeeves-agent-fr-filing`.

## Rules

- Roll back only the machine that failed; do not touch others mid-fleet.
- Never delete the backup folder after rollback.
- If ROLLBACK.ps1 itself fails or the previous build is also unhealthy: stop and escalate to Si with evidence.

## Stop rules

Never touch Ergo, AD/DNS/DHCP/SQL or protected processes. No secrets in the report.
