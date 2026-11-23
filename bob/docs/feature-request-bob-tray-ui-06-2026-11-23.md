# Feature request: Weights Refresh models button

**Repo:** `SimonBarnett/bobiverse`  
**ID:** `BOB-TRAY-UI-06`  
**Date:** 2026-11-23  
**Theme:** Systray cosmetic menu + icons + Weights refresh  
**Depends-on:** #9259  
**Skill:** visionary  
**Park:** park-only (hold until digest unhold)

## Objective

Deliver exactly one acceptance slice: Weights form Refresh models calls POST /bob/v1/models/refresh then GET and rebinds Model/Context/Effort dropdowns from clis. No validate POST.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Refresh rebinds | Button posts refresh, GET updates lastClis and combo options | Click Refresh after catalog change; inspect dropdown options / client unit test | No button, or Validate POST used, or dropdowns stale |

LOCKED

## Shape

Primary: app

Hybrid note: WinForms TipForm systray (`BobTray.cs`) + PowerShell tray parity (`Watch-BobTray.ps1`); Weights dialog.

LOCKED

## Stack

Default: existing bobiverse tray (.NET WinForms TipForm + PowerShell fallback). Prefer TipForm first; keep PS menu inventory in sync.

Why: TipForm is the live ContextMenuStrip with Seats/OpenCode keys/Exit siblings.

Why-not: new tray host; restore Validate POST on Weights.

LOCKED

## Architecture

`
TipForm ContextMenuStrip / About / WeightsForm
  -> BOB-TRAY-UI-06 change only (see Objective)
PS Watch-BobTray.ps1 mirrors menu inventory where it still builds a strip
`

LOCKED

## Screens

| id | file | state |
|----|------|-------|
| M1 | home.html | primary target menu / About / Weights as applicable |
| M2 | empty.html | missing icon asset / empty Workers |
| M3 | error.html | refresh or start failure surfaced without secrets |

## Gap

WeightsForm has Save/Close only; BobModelsClient has Get/Save.

## Out of scope

- Other BOB-TRAY-UI children except documented Depends-on
- seat_target semantics; Automatic engine fill policy
- POST /bob/v1/models/validate

## LOCKED

- One acceptance row only
- Park-only until digest unhold

## UNKNOWN

- Exact bob.ntsa.uk butler asset URL path (discover at implement for UI-09)