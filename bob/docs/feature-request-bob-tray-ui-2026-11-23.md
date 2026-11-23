# Feature request theme: Systray cosmetic menu + icons + Weights refresh

**Repo:** `SimonBarnett/bobiverse`  
**ID:** `BOB-TRAY-UI`  
**Date:** 2026-11-23  
**Theme:** Systray cosmetic menu + icons + Weights refresh  
**Skill:** visionary  
**Park:** park-only (fr-digest + hold)  
**Index:** `bob/docs/fr-index-bob-tray-ui-2026-11-23.md`

## Objective

Restructure the Bob TipForm systray menu (remove Seats/Open log/Automatic; Exit submenu; OpenCode Free|Paid; OpenCode keys on About), fix broken Agents/Workers icons (Cursor OK), flatten Priority, Jeeves butler from bob.ntsa.uk, make Plan/Priority clicks start seats, and add Weights Refresh models via POST /bob/v1/models/refresh.

LOCKED

## Success

Theme contract — delivered by child FRs:

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| T1 | Menu IA | Target menu tree in plan (no Seats/Open log/Automatic top; Exit submenu; OpenCode Free and Paid) | TipForm menu inventory test in `tests/` + `BobTray.cs` ContextMenuStrip walk | Old top items remain |
| T2 | Icons | Non-Cursor icons display; Priority=priority-mcp release; Jeeves=butler from bob.ntsa.uk | `Test-Path` on tray asset files under install dir + visual check | Broken/missing icons (except documented offline fallback) |
| T3 | Weights refresh | Refresh models updates dropdown catalogs from webhook | Click Refresh; `BobModelsClient` posts `/bob/v1/models/refresh` then GET rebinds combos | No refresh button or Validate POST returns |

LOCKED

## Shape

Primary: app

LOCKED

## Stack

Default: TipForm `BobTray.cs`, About, `WeightsForm.cs` / `BobModelsClient.cs`, `Watch-BobTray.ps1` parity.

LOCKED

## Architecture

`
Status
Agents { Plan, Priority(flat), Jeeves }
Workers { Grok, Cursor, OpenCode{Free,Paid} }
Weights (+ Refresh models)
About (Show logs + OpenCode keys)
—
Exit { Reload engine, Restart, Exit }
`

LOCKED

## Screens

| id | file | state |
|----|------|-------|
| M1 | home.html | target menu tree |
| M2 | empty.html | Workers with no Automatic |
| M3 | error.html | Weights refresh failure |

## Gap

TipForm still shows Seats, Open log, OpenCode keys, Automatic, flat Restart/Reload; Priority has Start/Configure MCP children; icons broken except Cursor; Weights has no Refresh models.

## Out of scope

seat_target behaviour; restoring Configure MCP elsewhere; models/validate POST.

## LOCKED

- Always-digest park; ten children
- TipForm primary

## UNKNOWN

- Exact bob.ntsa.uk butler URL