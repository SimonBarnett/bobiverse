# BOB-49 / FR #8700 / FR #9354 / FR #9468 / FR #9598 evidence: bob-ear MSI includes Plan agent + PlanAgent.exe

**Issue:** https://github.com/SimonBarnett/bobiverse/issues/8700  
**Vendor gap:** https://github.com/SimonBarnett/bobiverse/issues/9354  
**Tray vendor path:** https://github.com/SimonBarnett/bobiverse/issues/9468  
**Drop bob-plan twin:** https://github.com/SimonBarnett/bobiverse/issues/9598  
**Slice:** bob-ear MSI: include Plan agent build (Success S1) + skills-visionary PlanAgent.exe + `vendor/plan/PlanAgent.exe` only (never `bob-plan.exe`)

## S1

The bob product MSI stage (bob-ear pack) contains the **Plan** agent build under `plan\` and a verified **`plan\PlanAgent.exe`** from `SimonBarnett/skills-visionary` releases (tags `plan-*`). Pack also stages **`vendor/plan/PlanAgent.exe`** (single copy; FR #9598) so About/install discovery and Sync mirrors stay aligned. TipForm Plan clicks start **`vendor/plan/PlanAgent.exe`** (FR #9605; was `plan\PlanAgent.exe` in FR #9271 / BOB-TRAY-UI-10).

## How measured

1. `Stage-BobAgentFolders` (`Pack-BobiverseRelease.ps1`) syncs `bob-agents\plan` into the MSI stage and fails closed if `plan\AGENTS.md` is missing.
2. FR #9354: downloads `PlanAgent.exe` + `.sha256` from the skills-visionary release (tag from `BOB_PLAN_AGENT_RELEASE_TAG` or latest), verifies SHA-256, stages `plan\PlanAgent.exe`, and writes `plan\PlanAgent.MANIFEST.json` (tag, sha256, bytes, url).
3. Overrides: `BOB_PLAN_AGENT_EXE` / `OutDir\PlanAgent.exe`. Tests: `-SkipPlanAgentExe` (with `-SkipMsi`) uses fixture/MZ stub.
4. Marker `plan\BOB-49-PLAN-IN-MSI.txt` records vendor tag/sha256 so heat harvest / MSI file list includes Plan.
5. FR #9468 / #9598: `Copy-BobTrayVendorExes` mirrors `plan\PlanAgent.exe` into `vendor\plan\PlanAgent.exe` (+ MANIFEST, `.sha256` sidecar) and removes any leftover `bob-plan.exe` twin. Pack `-Require` fails if `vendor\plan\PlanAgent.exe` is absent or if `bob-plan.exe` is present. Sync mirrors when MSI left `plan\` on the install.
6. Tests pin the pack script contract (`test_fr8700_*`, `test_fr9354_*`, `test_fr9468_*`, `test_fr9271_*`).

## Fail-when

Plan tree or PlanAgent.exe missing from bob-ear MSI stage / sha256 mismatch / heat harvest miss / `vendor/plan/PlanAgent.exe` absent from stage / `vendor/plan/bob-plan.exe` still staged.

## Unblocks

FR #8833 (delete bobiverse Plan source copy after release vendoring).
