# Feature request: models webhook: valid combinations catalog

**Repo:** `SimonBarnett/bobiverse`  
**ID:** `BOB-03`  
**Phase:** `P0`  
**Date:** 2026-11-21  
**Theme:** Bob ear systray Agents/Workers/Weights + models webhook  
**Index:** `bob/docs/feature-request-systray-agents-workers-index-2026-11-21.md`  
**Depends-on:** BOB-01  
**Skill:** visionary  
**Park:** park-only (no bob-job-loop)

## Objective

Deliver exactly one acceptance slice: **models webhook: valid combinations catalog**.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Valid model/context/effort catalog per CLI | Invalid combo rejected; valid accepted | API rejects bad combo with 4xx; docs list valid keys — evidence in `docs/` + tray/log path | Invalid combo stored |

LOCKED

## Shape

Primary: service

Hybrid note: anti-omnibus slice of theme `Bob ear systray Agents/Workers/Weights + models webhook`; reuse existing SimonBarnett/bobiverse product surface.

LOCKED

## Stack

Default: existing SimonBarnett/bobiverse stack (Windows fleet, public GitHub, bob intake). This slice does not invent SaaS hosts or secrets.

Why: smallest shippable FR for anti-omnibus park.

Why-not: omnibus tray mega-issue.

LOCKED

## Architecture

```
theme brief -> BOB-03 slice -> SimonBarnett/bobiverse change surface
depends: BOB-01
```

LOCKED

## Screens

No new screens for this slice (non-UI). Shared theme mocks live in bobiverse `bob/docs/mocks/systray-agents-workers/` when UI.

| id | file | state |
|----|------|-------|
| M1 | (n/a) | n/a |

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
