# Feature request: Workers > Cursor: MarchHare token gate

**Repo:** `SimonBarnett/bobiverse`  
**ID:** `BOB-23`  
**Phase:** `P2`  
**Date:** 2026-11-21  
**Theme:** Bob ear systray Agents/Workers/Weights + models webhook  
**Index:** `bob/docs/feature-request-systray-agents-workers-index-2026-11-21.md`  
**Depends-on:** BOB-21  
**Skill:** visionary  
**Park:** park-only (no bob-job-loop)

## Objective

Deliver exactly one acceptance slice: **Workers > Cursor: MarchHare token gate**.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | MarchHare token gate | Dialog + quit when MarchHare has no tokens | Fuel fixture MarchHare=0 local may be 0; dialog shows | Gates on local box only |

LOCKED

## Shape

Primary: app

Hybrid note: anti-omnibus slice of theme `Bob ear systray Agents/Workers/Weights + models webhook`; reuse existing SimonBarnett/bobiverse product surface.

LOCKED

## Stack

Default: existing SimonBarnett/bobiverse stack (Windows fleet, public GitHub, bob intake). This slice does not invent SaaS hosts or secrets.

Why: smallest shippable FR for anti-omnibus park.

Why-not: omnibus tray mega-issue.

LOCKED

## Architecture

```
theme brief -> BOB-23 slice -> SimonBarnett/bobiverse change surface
depends: BOB-21
```

LOCKED

## Screens

HTML mocks (shared theme folder or local). Validator uses `--mocks-dir`.

| id | file | state |
|----|------|-------|
| M1 | home.html | primary |
| M2 | empty.html | empty |
| M3 | error.html | error |

## Gap vs current tree

See theme index. This issue owns only S1 above.

## Out of scope

Every other backlog ID. Implementation is after park when dispatched.

## LOCKED

- One acceptance row only
- Park-only until human dispatch
- Cross-link index + depends-on

## Implemented (FR #8719)

- Gate: `fleet-cursor-private.json` (MarchHare / si@ntsa.uk), never local `Get-BobTrayCursorFuelRemaining`
- Tray: `MarchHareCursorGate` + `Test-BobTrayMarchHareCursorExhausted` → dialog + quit (no start)
- Worker: refuse reason `MarchHare tokens exhausted` → `show_out_of_fuel_dialog` + `EXIT_OUT_OF_FUEL`
- Headless: `bob-tray.exe --check-marchhare-cursor-gate <out.json>`
- Test: `bob/tests/test_fr8719_marchhare_cursor_gate.py`
- Depends: BOB-21 (#8721)

## UNKNOWN

- Exact initial models matrix seed values (BOB-04) until CLI `--help` / Simon seed
- Favicon ToS for third-party sites when applicable
