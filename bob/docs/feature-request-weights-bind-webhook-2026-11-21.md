# Feature request: Weights form: bind to models webhook

**Repo:** `SimonBarnett/bobiverse`  
**ID:** `BOB-13`  
**Phase:** `P1`  
**Date:** 2026-11-21  
**Theme:** Bob ear systray Agents/Workers/Weights + models webhook  
**Index:** `bob/docs/feature-request-systray-agents-workers-index-2026-11-21.md`  
**Depends-on:** BOB-02, BOB-12  
**Skill:** visionary  
**Park:** park-only (no bob-job-loop)

## Objective

Deliver exactly one acceptance slice: **Weights form: bind to models webhook**.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Weights load/save via models webhook | Round-trip with /bob/v1/models | Save then reload matches GET — evidence in `docs/` + tray/log path | Local-only store |

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
theme brief -> BOB-13 slice -> SimonBarnett/bobiverse change surface
depends: BOB-02, BOB-12
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

## Implemented (FR #8714)

- Client: `bob/tray/dialogs/BobModelsClient.cs`
- Form + headless flags: `WeightsForm.cs`, `BobTray.cs` (`--weights-get` / `--weights-save`)
- Evidence: `bob/docs/evidence/bob13-weights-webhook-roundtrip-2026-11-22.md`
- Test: `bob/tests/test_bob13_weights_webhook_roundtrip.py`
- Depends: BOB-02 (#8708), BOB-12 (#8715); dialogs note in `bob-tray-dialogs.md`

## UNKNOWN

- Exact initial models matrix seed values (BOB-04) until CLI `--help` / Simon seed
- Favicon ToS for third-party sites when applicable
