# Feature request: models webhook: GET /bob/v1/models

**Repo:** `SimonBarnett/bobiverse`  
**ID:** `BOB-01`  
**Phase:** `P0`  
**Date:** 2026-11-21  
**Theme:** Bob ear systray Agents/Workers/Weights + models webhook  
**Index:** `bob/docs/feature-request-systray-agents-workers-index-2026-11-21.md`  
**Depends-on:** (none)  
**Skill:** visionary  
**Park:** park-only (no bob-job-loop)

## Objective

Deliver exactly one acceptance slice: **models webhook: GET /bob/v1/models**.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | GET /bob/v1/models returns fleet agent rows JSON | HTTP 200 JSON with agent rows (not 404) | `curl -sS -o NUL -w %{http_code} https://bob.ntsa.uk/bob/v1/models` and body schema check in `docs/` | 404 or empty/non-JSON body |

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
theme brief -> BOB-01 slice -> SimonBarnett/bobiverse change surface
depends: (none)
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
