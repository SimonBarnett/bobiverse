---
name: bobiverse-jeeves-agent-disk-starvation
description: >
  Detect worktree-create-failed:disk offer starvation on one machine, file one
  machine-pinned intake issue per machine per incident for the Jeeves agent, and
  auto-run the tokenless Clear/SeatDisk remediator (monitor disk_starvation).
  Use for disk-full idle seats, repeated disk NACKs, or /bobiverse-jeeves-agent-disk-starvation.
depends_on:
  - bobiverse-jeeves-agent-monitor
---

# bobiverse-jeeves-agent-disk-starvation

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. File every issue / FR / bug / gap you find in the SAME turn via the intake webhook (`https://bob.ntsa.uk/bob/v1/intake`):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
> 2. Before finishing, run `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "..." -Lesson "..."` then `-Flush`.
> 3. Never put a token, password, SASL/NickServ secret, oper credential, key or private hostname in a filing, a skill, IRC or a log.

Health context first: `bobiverse-jeeves-agent-monitor`. Class seen on flamingo (FR #6240 / #9692): every offer fails `worktree-create-failed:disk` / `disk-low`, seats look idle, MRBs pile up. Orphan `Users\*\.grok\bob-bridge\worktrees` leaves can dominate C: even after Clear reports removed=0.

## Detect

- Repeated offer failures with reason `worktree-create-failed:disk` / `disk-low` against **one machine** (live `/bob/v1/report` `giveup_reason` + `offer_outcomes`).
- Worktree path-collision reasons (`already used by worktree`, `is already checked out`, `worktree ... already exists`) do **not** trigger the check, even when the text also contains `worktree-create-failed:disk` (FR #9710).
- Map seats via `giveup_seats` as discrete seat-pid tokens only (a JSON string is one token - never character-split; FR #9728). Bare tokens and single-character / punctuation ids are skipped; never file intake for a non-fleet machine id (FR #9710).
- Seats on that machine stay idle while ungated offerable rows exist elsewhere.
- Flag once. Raise **one** bobiverse intake issue **per machine per incident** with a dedicated body line:
  `require_machine: <machine>`
  so the Jeeves agent / monitor owns it. Twin-check open issues first; comment on the first match. Do not open a second issue for the same machine+incident.

## Response order (hard)

1. **Tokenless monitor check** every cycle: `scripts\Invoke-JeevesMonitorCheck.ps1 -Check disk_starvation` (`tools\monitor\disk_starvation.py`). Prefer this over LLM reasoning.
2. On finding, the check **auto-runs** `common\scripts\Invoke-BobiverseDiskStarvationRemediate.ps1 -Machine <id>` (local or WinRM): FreeGB before, `Clear-BobiverseJobWorktrees -Force`, `Clear-BobiverseSeatDisk -Reclaim`, orphan bob-bridge job leaves, FreeGB after. Set `BOB_DISK_STARVATION_AUTO=0` for detect-only.
3. File / refresh the machine-pinned intake issue (check does this with a cooldown stamp unless `BOB_DISK_STARVATION_FILE=0`).
4. After space recovers: `!cleargiveup` disk-low rows for that machine, then feed idle seats.

LLM / Slab path remains valid when WinRM is down or FreeGB stays critical after the remediator: post FreeGB + top consumers, escalate, never touch Ergo.

## Safe cleanup scope (remediator / Slab)

| Allowed | Forbidden |
|---|---|
| Stale job worktrees no running job uses (`Clear-BobiverseJobWorktrees.ps1`) | Worktrees for running jobs / live `.bobiverse-seat` with live pid (fresh marker) |
| Aged TEMP leftovers (`bobiverse-*` / `fr-*` / `mrb-*` / `pytest-of-*` via SeatDisk) | Seats themselves (`bob-worker.exe`, shop processes) |
| Orphan `cdk.out` under job trees (FR #3717 `cmd rmdir`) | Install roots / product repos (`C:\ai\bob`, `C:\ai\jeeves`, ...) |
| Orphan `Users\*\.grok\bob-bridge\worktrees\...\(fr|mrb|fix|uat|job)-*` leaves | `D:\ai` config trees the operator did not name |
| | Ergo / `BobIrcd` / unrelated services |
| | Reboot |

Never invent a hand `Remove-Item` list of `C:\ai\*` wt trees (FR #2727). Prefer Clear + SeatDisk + bob-bridge orphan pass.

## Verify

1. Record FreeGB before and after on the same volume.
2. Confirm the machine's seats take offers again (an offer ACK with no `worktree-create-failed:disk`).
3. Report both numbers and the first successful ACK on the machine-pinned issue.

## Prevention (product)

- Chair: on disk GIVEUP/NACK, auto-file the machine-pinned issue (`require_machine: <machine>`) if missing.
- Monitor: `disk_starvation` every cycle (this skill).
- Candidate FR: warn before the disk fills; prune stale worktrees after DONE without waiting for starvation.

## Stop rules

- Stop if the next step would touch a live job tree, a seat process, a repo install root, or Ergo.
- One intake issue per machine per incident; comment on twins.
- Detect-only when `BOB_DISK_STARVATION_AUTO=0`.
