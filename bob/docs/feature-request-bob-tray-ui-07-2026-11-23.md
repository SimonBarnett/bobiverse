# Feature request: Re-import broken menu icons

**Repo:** `SimonBarnett/bobiverse`  
**ID:** `BOB-TRAY-UI-07`  
**Date:** 2026-11-23  
**Theme:** Systray cosmetic menu + icons + Weights refresh  
**Depends-on:** #9259  
**Skill:** visionary  
**Park:** park-only (hold until digest unhold)

## Objective

Deliver exactly one acceptance slice: fix/re-vendor Workers and Agents menu icons so all except Cursor display correctly (Grok, OpenCode, Priority, Jeeves, Plan). Cursor unchanged. Log loud if asset missing.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Icons visible | Non-Cursor menu icons render from reliable install assets | Visual check + `Test-Path` asserts in `tests/` on vendored `.ico` assets | Broken/blank icons remain for non-Cursor rows |

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
  -> BOB-TRAY-UI-07 change only (see Objective)
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

Favicon/butler/priority paths fail at runtime; only Cursor works.

## Out of scope

- Other BOB-TRAY-UI children except documented Depends-on
- seat_target semantics; Automatic engine fill policy
- POST /bob/v1/models/validate

## LOCKED

- One acceptance row only
- Park-only until digest unhold

## UNKNOWN

- Exact bob.ntsa.uk butler asset URL path (discover at implement for UI-09)