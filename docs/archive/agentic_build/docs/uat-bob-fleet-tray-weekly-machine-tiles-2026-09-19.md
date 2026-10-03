<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/uat-bob-fleet-tray-weekly-machine-tiles-2026-09-19.md, last changed 2026-09-19. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# UAT - Bob Fleet tray weekly remaining + machine tiles (2026-09-19)

**Repo:** SimonBarnett/agentic_build  
**Tip:** `c31b0ed` Tray: weekly remaining bar + machine tiles (FR T1-T7)  
**FR:** docs/feature-request-bob-fleet-tray-weekly-machine-tiles-2026-09-19.md (park commit 7e8797e)  
**Host:** ionos (`WIN-MPRE8VI4U6U`) ~2026-09-19 22:04 BST  
**Surface:** `Get-BobTrayHover`, `Get-BobBoxUsage.ps1 -Hover`, live `unified.jsonl` billing line

Hover card notes (WinForms paint uses this object; live mouse-over of the robot is after Watch-BobTray recycle).

## Live hover object

```
title: Bob Fleet
machine: ionos
scope: local-store
short: P+ 1 run  48%
remaining_pct: 48
remaining_kind: weekly
weekly_fetched_at: 2026-09-19T18:16:51.807Z
jobs_text:
  ionos
    SimonBarnett/agentic_build  5m  running
  other hosts not in this store
```

## T1-T7

| ID | Gate | Live |
|---|---|---|
| T1 | Title Bob Fleet, not Bob (ionos) | `title=Bob Fleet` |
| T2 | Machine tile with jobs underneath | `ionos` heading then indented job line |
| T3 | owner/repo, not SHA | `SimonBarnett/agentic_build` (this job cwd) |
| T4 | Primary bar weekly remaining | `remaining_kind=weekly`, caption path `Weekly remaining`, fill from 48% |
| T5 | Local-store honesty | `scope=local-store`, footer `other hosts not in this store` (only ionos in this store) |
| T6 | Short tip 63 chars | `P+ 1 run  48%` (22 chars) |
| T7 | Park-once / no cursor-chase | unchanged; BT0m/BT0n still pass |

## Weekly signal (not invented)

Last `billing: fetched credits config` in `~\.grok\logs\unified.jsonl`:

- `creditUsagePercent`: 52.0
- `currentPeriod.type`: `USAGE_PERIOD_TYPE_WEEKLY`
- remaining = round(100 - 52) = **48%**
- Same field the Grok CLI footer prints as `Weekly limit left: N%`
- Session context 233K/500K is **not** this bar (`context_remaining_pct` on the job is null; hover `remaining_kind=weekly`)

`Get-BobBoxUsage` text: `Weekly: remaining 48% (used 52%) source=unified.jsonl:billing: fetched credits config`

## Offline

Test-Pack **BT0 15 pass / 0 fail** including BT0l (weekly + tiles), BT0m (park-once), BT0n (ShowParkedAt).

## Ops

- Did **not** `Stop-ScheduledTask BobFleet-ionos` (job `21c8450f` running).
- Watch-BobTray was not live at UAT (task Ready). Recycle = start hidden STA `Watch-BobTray.ps1` only.
- Two `Watch-BobJobs.ps1` (non-Once) processes left untouched.

## Hover card notes (ok)

Dark card should paint:

1. Title **Bob Fleet**
2. Caption **Weekly remaining    48%** with a ~48% fill (green; not the old Context remaining bar)
3. Tile **ionos** then `SimonBarnett/agentic_build  <duration>  running`
4. Line `other hosts not in this store`
5. Footer `alert: none` (48% is not &lt;10%)
6. Short NotifyIcon.Text `P+ 1 run  48%`

If weekly log missing: caption `Weekly remaining  n/a`, track hidden, no depleted fill.
