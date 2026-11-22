# Feature request: Systray hover xAI weekly matches Usage dialog (label xAI not SG)

**Repo:** SimonBarnett/bobiverse  
**ID:** BOB-HOVER-XAI  
**Date:** 2026-11-22  
**Theme:** Bob ear systray hover honesty  
**Depends-on:** (none)  
**Skill:** visionary  
**Park:** park-only; label hold

## Objective

NotifyIcon hover ToolTip must show this machine's **xAI weekly** remaining % equal to the Status/Usage dialog xAI weekly value for the same machine, and must label the pool **xAI** (never **SG** / SuperGrok abbreviation).

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Hover % and label match Usage xAI weekly | Same paint cycle: hover `short` % == Status xAI weekly remaining % for this machine; hover uses label `xAI` not `SG` | Fixture/pytest: same digest `machines.<id>.xai_weekly.remaining_pct` drives hover `short` and Status Usage row; string assert hover short/body contains `xAI` and does not contain standalone `SG` as the pool tier | Hover % differs from Status xAI weekly for this host; or hover still shows `SG` for SuperGrok/xAI weekly |

LOCKED

## Shape

Primary: service

Hybrid note: tray hover + Status paint on existing bob-tray / Get-BobTrayHover.

UNKNOWN

## Stack

Existing bobiverse tray (bob-tray.exe, Watch-BobTray, Get-BobTrayHover.ps1).

Why: smallest honesty fix for operators reading hover vs Status.

Why-not: rewrite TipForm layout or change digest schema.

LOCKED

## Architecture

```
digest machines.<m>.xai_weekly.remaining_pct
        |
        +--> Status/Usage xAI weekly row (existing Format-BobTrayXaiWeeklyRow)
        |
        +--> NotifyIcon hover short/body (same remaining_pct; tier label "xAI" not "SG")
```

LOCKED

## Screens

No new screens.

| id | file | state |
|----|------|-------|
| M1 | (n/a) | n/a |

## Gap

Hover `short` embeds `$remainPct` and `$tier` where SuperGrok maps to `SG` (Get-BobTrayHover.ps1). Operators see hover % or label disagree with Status Usage xAI weekly for the machine. Hover must always show this machine's xAI weekly, labeled xAI.

## Out of scope

Cursor Spending CAST IRON fuel-gate changes. Copilot/OpenCode hover lines. Digest schema. Menu structure FRs.

## LOCKED

- One acceptance row
- Source of truth for the %: same xAI weekly reading Status uses for this machine (`machines.<id>.xai_weekly`)
- Display label in hover: `xAI` (replace `SG` for SuperGrok / xAI weekly tier)
- NotifyIcon.Text still <= 63 chars

## UNKNOWN

- Whether peer hover peek needs the same label change (implementer: yes if peer short uses same `$tier` map)