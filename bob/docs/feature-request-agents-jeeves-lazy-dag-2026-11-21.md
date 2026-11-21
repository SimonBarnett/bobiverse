# Feature request: Agents > Jeeves: lazy-load skill DAG

**Repo:** `SimonBarnett/bobiverse`  
**ID:** `BOB-39`  
**Phase:** `P3`  
**Date:** 2026-11-21  
**Theme:** Bob ear systray Agents/Workers/Weights + models webhook  
**Index:** `bob/docs/feature-request-systray-agents-workers-index-2026-11-21.md`  
**Depends-on:** BOB-38  
**Skill:** visionary  
**Park:** park-only (no bob-job-loop)

## Objective

Deliver exactly one acceptance slice: **Agents > Jeeves: lazy-load skill DAG**.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Jeeves skills lazy DAG | DAG lazy-load works | DAG check/smoke on J: skills | Eager full load only / no DAG |

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
theme brief -> BOB-39 slice -> SimonBarnett/bobiverse change surface
depends: BOB-38
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
