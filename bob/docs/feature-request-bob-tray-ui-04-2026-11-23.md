# Feature request: OpenCode keys on About

**Repo:** `SimonBarnett/bobiverse`  
**ID:** `BOB-TRAY-UI-04`  
**Date:** 2026-11-23  
**Theme:** Systray cosmetic menu + icons + Weights refresh  
**Depends-on:** #9259  
**Skill:** visionary  
**Park:** park-only (hold until digest unhold)

## Objective

Deliver exactly one acceptance slice: remove top-level OpenCode keys; About gains a button that opens the same key set/select/remove UI as today.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Keys on About | No top OpenCode keys; About button opens key UI | TipForm menu inventory + About dialog click in `BobTray.cs` / About form | OpenCode keys still top-level or About has no button |

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
  -> BOB-TRAY-UI-04 change only (see Objective)
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

BobTray.cs MenuItems OpenCode keys at top.

## Out of scope

- Other BOB-TRAY-UI children except documented Depends-on
- seat_target semantics; Automatic engine fill policy
- POST /bob/v1/models/validate

## LOCKED

- One acceptance row only
- Park-only until digest unhold

## UNKNOWN

- Exact bob.ntsa.uk butler asset URL path (discover at implement for UI-09)