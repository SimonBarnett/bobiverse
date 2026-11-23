# BOB-49 / FR #8700 / FR #9354 / FR #9468 evidence: bob-ear MSI includes Plan agent + PlanAgent.exe + tray vendor path

**Issue:** https://github.com/SimonBarnett/bobiverse/issues/8700  
**Vendor gap:** https://github.com/SimonBarnett/bobiverse/issues/9354  
**Tray vendor path:** https://github.com/SimonBarnett/bobiverse/issues/9468  
**Slice:** bob-ear MSI: include Plan agent build (Success S1) + skills-visionary PlanAgent.exe + `vendor/plan/bob-plan.exe`

## S1

The bob product MSI stage (bob-ear pack) contains the **Plan** agent build under `plan\` and a verified **`plan\PlanAgent.exe`** from `SimonBarnett/skills-visionary` releases (tags `plan-*`). Pack also stages **`vendor/plan/bob-plan.exe`** (and `PlanAgent.exe` twin) so TipForm Plan clicks resolve without a manual hotpatch.

## How measured

1. `Stage-BobAgentFolders` (`Pack-BobiverseRelease.ps1`) syncs `bob-agents\plan` into the MSI stage and fails closed if `plan\AGENTS.md` is missing.
2. FR #9354: downloads `PlanAgent.exe` + `.sha256` from the skills-visionary release (tag from `BOB_PLAN_AGENT_RELEASE_TAG` or latest), verifies SHA-256, stages `plan\PlanAgent.exe`, and writes `plan\PlanAgent.MANIFEST.json` (tag, sha256, bytes, url).
3. Overrides: `BOB_PLAN_AGENT_EXE` / `OutDir\PlanAgent.exe`. Tests: `-SkipPlanAgentExe` (with `-SkipMsi`) uses fixture/MZ stub.
4. Marker `plan\BOB-49-PLAN-IN-MSI.txt` records vendor tag/sha256 so heat harvest / MSI file list includes Plan.
5. FR #9468: `Copy-BobTrayVendorExes` mirrors `plan\PlanAgent.exe` into `vendor\plan\bob-plan.exe` (+ `PlanAgent.exe`, MANIFEST, `.sha256` sidecar). Pack `-Require` fails if the tray path is absent. Sync mirrors when MSI left `plan\` on the install.
6. Tests pin the pack script contract (`test_fr8700_*`, `test_fr9354_*`, `test_fr9468_*`).

## Fail-when

Plan tree or PlanAgent.exe missing from bob-ear MSI stage / sha256 mismatch / heat harvest miss / `vendor/plan/bob-plan.exe` absent from stage.

## Unblocks

FR #8833 (delete bobiverse Plan source copy after release vendoring).
