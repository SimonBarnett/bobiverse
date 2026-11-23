# Feature request: Weights — no POST /models/validate

**Repo:** `SimonBarnett/bobiverse`  
**ID:** `BOB-WEIGHTS-NO-VALIDATE`  
**Phase:** `P0`  
**Date:** 2026-11-22  
**Theme:** Bob ear systray Agents/Workers/Weights + models webhook  
**Depends-on:** `#8716`  
**Skill:** visionary  
**Park:** park-only (no bob-job-loop until unhold)

## Objective

Stop the Weights UI and workers from calling or advertising `POST /bob/v1/models/validate`. Validation is form-only via GET `/bob/v1/models` catalog dropdowns.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | No Validate POST path | Weights has no Validate button and no client POST to `/bob/v1/models/validate`; save uses GET+PUT `/bob/v1/models` only | Grep tray/worker + manual Weights open; POST returns 404 `no_models_validate` if probed | Validate button visible, subtitle shows POST validate, or client issues that POST |

LOCKED

## Shape

Primary: app

Hybrid note: anti-omnibus FIX against wrong Validate POST; docs already dropped the Models validate card (#9024). Reuse SimonBarnett/bobiverse tray surface.

LOCKED

## Stack

Default: existing SimonBarnett/bobiverse stack (Windows fleet, public GitHub, bob intake). This slice does not invent SaaS hosts or secrets.

Why: smallest shippable FR to stop the wrong Validate POST.

Why-not: omnibus Weights redesign.

LOCKED

## Architecture

```
Weights UI -> GET /bob/v1/models (clis catalog + current rows)
          -> dropdowns only from clis[row.cli]
          -> PUT /bob/v1/models on Save
Never -> POST /bob/v1/models/validate
Backend already 404s validate (bobcallback); clients must stop calling it.
```

LOCKED

## Screens

HTML mocks under `bob/docs/mocks/weights-no-validate/`. Validator uses `--mocks-dir`.

| id | file | state |
|----|------|-------|
| M1 | home.html | primary — Save/Cancel only; subtitle GET\|PUT models |
| M2 | empty.html | empty catalog / no rows |
| M3 | error.html | GET models failed |

## Gap vs current tree

- Live Weights dialog (2026-11-22 screenshot) still subtitled `POST /bob/v1/models/validate` with a **Validate** button.
- #8716 body already LOCKED: no POST validate; form dropdowns are validation — workers still shipped/serviced the wrong path.
- Public docs (#9024) removed Models validate card; tray/workers did not follow.

## Acceptance

1. Remove Validate button and any POST `/bob/v1/models/validate` client code from Weights / workers.
2. Dialog chrome must not mention POST validate; Save PUTs `/bob/v1/models` after GET catalog bind.
3. Evidence: screenshot of Weights without Validate; grep clean for `models/validate` in bob tray/worker; optional curl POST still 404.

## Out of scope

- Redesigning the full Weights grid (BOB-12 closed).
- Catalog refresh `POST /bob/v1/models/refresh` (#8820) — different endpoint.

## LOCKED

- One acceptance row only
- Park-only until human unhold / dispatch
- Depends-on #8716 (valid-only dropdowns clarification)

## UNKNOWN

- Exact file that currently paints the Validate dialog (not in main tray BobTrayDialogs about/status-only surface at park time)
