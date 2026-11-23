# BOB-49 / FR #8700 / FR #9354 evidence: bob-ear MSI includes Plan agent + PlanAgent.exe

**Issue:** https://github.com/SimonBarnett/bobiverse/issues/8700  
**Vendor gap:** https://github.com/SimonBarnett/bobiverse/issues/9354  
**Slice:** bob-ear MSI: include Plan agent build (Success S1) + skills-visionary PlanAgent.exe

## S1

The bob product MSI stage (bob-ear pack) contains the **Plan** agent build under `plan\` and a verified **`plan\PlanAgent.exe`** from `SimonBarnett/skills-visionary` releases.

## How measured

1. `Stage-BobAgentFolders` (`Pack-BobiverseRelease.ps1`) syncs `bob-agents\plan` into the MSI stage and fails closed if `plan\AGENTS.md` is missing.
2. FR #9354: downloads `PlanAgent.exe` + `.sha256` from the skills-visionary release (tag from `BOB_PLAN_AGENT_RELEASE_TAG` or latest), verifies SHA-256, stages `plan\PlanAgent.exe`, and writes `plan\PlanAgent.MANIFEST.json` (tag, sha256, bytes, url).
3. Overrides: `BOB_PLAN_AGENT_EXE` / `OutDir\PlanAgent.exe`. Tests: `-SkipPlanAgentExe` (with `-SkipMsi`) uses fixture/MZ stub.
4. Marker `plan\BOB-49-PLAN-IN-MSI.txt` records vendor tag/sha256 so heat harvest / MSI file list includes Plan.
5. Tests pin the pack script contract (`test_fr8700_*`, `test_fr9354_*`).

## Fail-when

Plan tree or PlanAgent.exe missing from bob-ear MSI stage / sha256 mismatch / heat harvest miss.

## Unblocks

FR #8833 (delete bobiverse Plan source copy after release vendoring).
