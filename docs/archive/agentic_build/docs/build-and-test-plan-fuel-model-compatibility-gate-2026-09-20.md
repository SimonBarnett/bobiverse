<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/build-and-test-plan-fuel-model-compatibility-gate-2026-09-20.md, last changed 2026-09-20. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: fuel/model compatibility gate (issue #17)

**Date:** 2026-09-20  
**Repo:** https://github.com/SimonBarnett/agentic_build  
**Issue:** https://github.com/SimonBarnett/agentic_build/issues/17  
**Spec:** `docs/feature-request-fuel-model-compatibility-gate-2026-09-20.md`  
**Chair:** Bob (hostile MRB on #17). Builder opens PR; never push `main`; never merge.

## Goals

- Refuse mismatched `-Fuel` / `-Model` at `Start-BobBuild` enqueue.
- Refuse mismatched `fuel` / `model` on fleet tick before `Start-BobWorker`.
- Single mapping in `config/default.json` (`fuelModelFamilies`, `modelFamilies`).

## Non-goals

- Changing locked `models.*` values or MRB default model selection logic beyond compatibility checks.
- Downgrading mismatches to fuel defaults (enqueue hard-refuses).

## Implementation

1. Add `Get-BobFuelModelConfig` + `Test-BobFuelModelCompatible` (module surface: `Test-BobFuelModelCompatible`).
2. `Start-BobBuild`: after model resolution, call test; return `ok=$false`, `error=fuel_model_mismatch`.
3. `Invoke-BobFleetOnce`: before moving to `running`, fail packet with `completion.summary` naming mismatch.
4. Config: `fuelModelFamilies` + regex `modelFamilies` per family (`cursor`, `grok`, `none`).

## Tests (off-DEV)

Run from repo root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\Test-Pack.ps1
```

| ID | Case | Acceptance |
|---|---|---|
| BT0x1 | fuel model enqueue refuse | AC1 |
| BT0x2 | fuel model tick refuse | AC2 (no fake grok session growth) |
| BT0x3 | fuel model matched enqueue | AC3 + all fuels |
| BT0x4 | fuel model matched tick | matched grok-build completes ok |

## Done when

FR acceptance AC1–AC4 true. `tools/Test-Pack.ps1` green. PR open for Bob MRB on #17. No human UAT stamp.
