# BOB-55 / FR #8701 / FR #9354 evidence: bob-ear MSI includes PriorityAgent.exe

**Issue:** https://github.com/SimonBarnett/bobiverse/issues/8701  
**Vendor align:** https://github.com/SimonBarnett/bobiverse/issues/9354  

## S1

The bob product MSI stage includes `priority\PriorityAgent.exe`.

## How measured

1. `Stage-BobAgentFolders` stages `priority\PriorityAgent.exe`.
2. FR #9354: when env/OutDir override is absent, downloads `PriorityAgent.exe` + `.sha256` from `SimonBarnett/priority-mcp` releases (tag from `BOB_PRIORITY_AGENT_RELEASE_TAG` or latest), verifies SHA-256, writes `priority\PriorityAgent.MANIFEST.json`.
3. Overrides: `BOB_PRIORITY_AGENT_EXE` / `OutDir\PriorityAgent.exe`. Tests: `-SkipPriorityExe` (with `-SkipMsi`) uses fixture/MZ stub.
4. Marker `priority\BOB-55-PRIORITY-IN-MSI.txt` records vendor tag/sha256.

## Fail-when

PriorityAgent.exe missing from bob-ear MSI stage / sha256 mismatch.
