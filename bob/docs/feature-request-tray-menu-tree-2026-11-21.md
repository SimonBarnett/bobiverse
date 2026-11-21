# Feature request: Tray menu tree: Status/Agents/Workers/Weights/About/Exit

**Repo:** `SimonBarnett/bobiverse`  
**ID:** `BOB-06`  
**Phase:** `P1`  
**Date:** 2026-11-21  
**Theme:** Bob ear systray Agents/Workers/Weights + models webhook  
**Index:** `bob/docs/feature-request-systray-agents-workers-index-2026-11-21.md`  
**Depends-on:** (none)  
**Skill:** visionary  
**Park:** park-only (no bob-job-loop)

## Objective

Deliver exactly one acceptance slice: **Tray menu tree: Status/Agents/Workers/Weights/About/Exit**.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Context menu structure matches brief | Menu tree Status→Agents{Plan,Priority,Jeeves}→Workers{Grok,Cursor,Open Code}→Weights→About→Exit | Tray UAT checklist vs `docs/mocks/systray-agents-workers/home.html` | Flat Plan sibling or missing Weights/Exit |

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
theme brief -> BOB-06 slice -> SimonBarnett/bobiverse change surface
depends: (none)
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

## UNKNOWN

- Exact initial models matrix seed values (BOB-04) until CLI `--help` / Simon seed
- Favicon ToS for third-party sites when applicable
