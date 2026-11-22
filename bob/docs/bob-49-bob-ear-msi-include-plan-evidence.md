# BOB-49 / FR #8700 evidence: bob-ear MSI includes Plan agent build

**Issue:** https://github.com/SimonBarnett/bobiverse/issues/8700  
**Slice:** bob-ear MSI: include Plan agent build (Success S1)

## S1

The bob product MSI stage (bob-ear pack) contains the **Plan** agent build under `plan\`.

## How measured

1. `Stage-BobAgentFolders` (`Pack-BobiverseRelease.ps1`) syncs `bob-agents\plan` into the MSI stage and fails closed if `plan\AGENTS.md` is missing.
2. Marker `plan\BOB-49-PLAN-IN-MSI.txt` is written so heat harvest / MSI file list includes Plan.
3. Tests pin the pack script contract.

## Fail-when

Plan missing from bob-ear MSI stage / heat harvest.