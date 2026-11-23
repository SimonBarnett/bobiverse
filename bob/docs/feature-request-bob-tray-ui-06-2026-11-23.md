# Feature request: Weights Refresh models button

**Repo:** `SimonBarnett/bobiverse`  
**ID:** `BOB-TRAY-UI-06`  
**Date:** 2026-11-23  
**Theme:** Systray cosmetic menu + icons + Weights refresh  
**Depends-on:** #9259  
**Skill:** visionary  
**Park:** park-only (hold until digest unhold)

## Objective

Deliver exactly one acceptance slice: Weights form **Refresh models** discovers available models on this machine via the local CLI APIs (Grok / Cursor / OpenCode), **POSTs that catalog to the models webhook**, then GETs and rebinds Model/Context/Effort dropdowns. The tray/Weights client owns discovery and POST; Ergo/chair does not run CLIs (no tokens on the DC). No validate POST. Supersedes Bob-ear catalogue reporting (#9250 closed not-planned).

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Client posts catalog then rebinds | Refresh runs local model listing APIs, POSTs discovered `clis` to `/bob/v1/models` (or documented refresh route that accepts client-supplied catalog), then GET updates lastClis and combo options | Click Refresh; network/trace shows client→webhook POST body with models; dropdown options match POST; `BobModelsClient` unit test | No button; chair/Ergo shells CLIs; Validate POST used; dropdowns stale; Bob ear is the publisher |

LOCKED

## Shape

Primary: app

Hybrid note: WinForms TipForm systray (`BobTray.cs`) + PowerShell tray parity (`Watch-BobTray.ps1`); Weights dialog.

LOCKED

## Stack

Default: existing bobiverse tray (.NET WinForms TipForm + PowerShell fallback). Prefer TipForm first; keep PS menu inventory in sync.

Why: TipForm/WeightsForm runs on fleet seats that already have signed-in CLIs; Ergo (walrus) does not.

Why-not: chair-side CLI refresh; Bob-ear periodic catalogue push (#9250); restore Validate POST on Weights.

LOCKED

## Architecture

`
WeightsForm Refresh models
  -> local CLI model APIs (this machine)
  -> POST catalog to models webhook (bob.ntsa.uk /bob/v1/models…)
  -> GET /bob/v1/models
  -> rebind Model/Context/Effort combos
Ergo/chair: store/merge only — never spawn grok/cursor/opencode
`
LOCKED

## Screens

| id | file | state |
|----|------|-------|
| M1 | home.html | primary target menu / About / Weights as applicable |
| M2 | empty.html | missing icon asset / empty Workers |
| M3 | error.html | refresh or start failure surfaced without secrets |

## Gap

WeightsForm has Save/Close only; BobModelsClient has Get/Save. Live `POST /bob/v1/models/refresh` still assumes chair-side CLI listing (#8820 era), which fails on walrus (`not_installed`). #9250 proposed Bob ear as publisher — replaced by this Weights button path.

## Out of scope

- Other BOB-TRAY-UI children except documented Depends-on
- seat_target semantics; Automatic engine fill policy
- POST /bob/v1/models/validate
- Bob-ear periodic or on-demand catalogue reporting (#9250)

## LOCKED

- One acceptance row only
- Park-only until digest unhold
- Client posts available models; Ergo does not discover them

## UNKNOWN

- Exact POST body shape vs existing refresh route (extend refresh to accept client catalog, or PUT `clis` — pick in implement PR and document)
