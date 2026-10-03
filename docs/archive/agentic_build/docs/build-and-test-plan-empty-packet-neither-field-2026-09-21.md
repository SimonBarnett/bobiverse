<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/build-and-test-plan-empty-packet-neither-field-2026-09-21.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: empty packet neither fuel nor model (issue #79)

**Date:** 2026-09-21  
**Repo:** https://github.com/SimonBarnett/agentic_build  
**Issue:** https://github.com/SimonBarnett/agentic_build/issues/79  
**Spec:** `docs/feature-request-empty-packet-neither-field-2026-09-21.md`  
**Chair:** Bob (hostile MRB on #79). Builder opens PR; never push `main`; never merge.

## Goals

- Lock tick path for hand-written inbox packets with **neither** `fuel` nor `model`: refuse at
  fleet tick before `Start-BobWorker` (no historic `grok-build` default).
- Named completion summary: `missing_fuel_and_model`.
- Preserve issue #54: non-empty `model` and no `fuel` still fails with `missing_fuel model=…`.

## Implementation

1. `Test-BobPacketMissingFuel`: when fuel absent and model absent, return `ok=false` and
   `missing_fuel_and_model`.
2. `Invoke-BobFleetOnce`: unchanged call site (already fails on `ok=false` before `running`).

## Tests (off-DEV)

| ID | Case | Acceptance |
|---|---|---|
| BT0z1 | empty fuel and model tick refuse | AC1–AC2 (no Fake-Grok session growth) |
