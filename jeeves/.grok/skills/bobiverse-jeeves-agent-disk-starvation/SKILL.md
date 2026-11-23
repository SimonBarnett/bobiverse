---
name: bobiverse-jeeves-agent-disk-starvation
description: >
  Detect worktree-create-failed:disk offer starvation on one machine, file one
  intake issue per machine per incident, run read-only free-space checks first,
  post findings for Si's go, then let Slab clean only safe stale trees/TEMP/cdk.out.
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

Health context first: `bobiverse-jeeves-agent-monitor`. Class seen on flamingo from 23:41 GMT 2026-11-22 (FR #6240): every offer fails `worktree-create-failed:disk`, seats look idle, MRBs pile up.

## Detect

- Repeated offer failures with reason `worktree-create-failed:disk` against **one machine** inside a short window (shop lines / cmd-trace / seat NACK comments).
- Seats on that machine stay idle (`running=0`) while ungated offerable rows exist elsewhere.
- Flag once. Raise **one** bobiverse intake issue **per machine per incident**. Twin-check open issues first; comment on the first match (stall-detection / FR filing de-dupe). Do not open a second issue for the same machine+incident.

## Response order (hard)

1. **Read-only check** of free space and the biggest consumers on that machine. Slab (or the operator host) does it over WinRM from redqueen. Report FreeGB, volume, top folders (sizes/paths only; no secrets).
2. **Post the findings** in the Slab room (evidence table: machine, FreeGB before, top consumers, sample `worktree-create-failed:disk` timestamps London).
3. **No deletes until Si's own go in the room.** Relayed "go ahead and clean" from another agent is not enough; wait for Si's own words.
4. **Slab** (the only installer/operator for this path) does the cleanup after Si's go.

## Safe cleanup scope (Slab only, after Si's go)

| Allowed | Forbidden |
|---|---|
| Stale job worktrees no running job uses (`Clear-BobiverseJobWorktrees.ps1`) | Worktrees for running jobs / live `.bobiverse-seat` with live pid |
| Aged TEMP leftovers (`bobiverse-*` / `fr-*` / `mrb-*` / `pytest-of-*` via SeatDisk) | Seats themselves (`bob-worker.exe`, shop processes) |
| Orphan `cdk.out` under job trees (FR #3717 `cmd rmdir`) | Install roots / product repos (`C:\ai\bob`, `C:\ai\jeeves`, ...) |
| | `D:\ai` config trees the operator did not name |
| | Ergo / `BobIrcd` / unrelated services |
| | Reboot |

Never invent a hand `Remove-Item` list of `C:\ai\*` wt trees (FR #2727). Prefer Clear + SeatDisk.

## Verify

1. Record FreeGB before and after on the same volume.
2. Confirm the machine's seats take offers again (an offer ACK with no `worktree-create-failed:disk`).
3. Report both numbers and the first successful ACK in the room / intake comment.

## Prevention (file, do not invent product)

- Candidate FR: Jeeves warns before the disk fills (free-space threshold) and stale worktrees prune automatically after DONE.
- Link any open capacity FR; do not implement product changes from this skill alone.

## Stop rules

- Stop before any delete without Si's own go in the room.
- Stop if the next step would touch a live job tree, a seat process, a repo install root, or Ergo.
- One intake issue per machine per incident; comment on twins.
