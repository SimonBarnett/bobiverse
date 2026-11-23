# BOB-55 / FR #8701 / FR #9354 / FR #9468 evidence: bob-ear MSI includes PriorityAgent.exe + tray vendor path

**Issue:** https://github.com/SimonBarnett/bobiverse/issues/8701  
**Vendor align:** https://github.com/SimonBarnett/bobiverse/issues/9354  
**Tray vendor path:** https://github.com/SimonBarnett/bobiverse/issues/9468  

## S1

The bob product MSI stage includes `priority\PriorityAgent.exe` from `SimonBarnett/priority-mcp` releases (tags `launcher-*`). Pack also stages **`vendor/priority/PriorityAgent.exe`** so TipForm Priority clicks resolve without a manual hotpatch. No separate PriorityClient.exe product path (airc S1 stays in-service).

## How measured

1. `Stage-BobAgentFolders` stages `priority\PriorityAgent.exe`.
2. FR #9354: when env/OutDir override is absent, downloads `PriorityAgent.exe` + `.sha256` from `SimonBarnett/priority-mcp` releases (tag from `BOB_PRIORITY_AGENT_RELEASE_TAG` or latest), verifies SHA-256, writes `priority\PriorityAgent.MANIFEST.json`.
3. Overrides: `BOB_PRIORITY_AGENT_EXE` / `OutDir\PriorityAgent.exe`. Tests: `-SkipPriorityExe` (with `-SkipMsi`) uses fixture/MZ stub.
4. Marker `priority\BOB-55-PRIORITY-IN-MSI.txt` records vendor tag/sha256.
5. FR #9468: `Copy-BobTrayVendorExes` mirrors into `vendor\priority\PriorityAgent.exe` (+ MANIFEST, `.sha256` sidecar). Pack `-Require` fails if the tray path is absent. Sync mirrors when MSI left `priority\` on the install.
6. Tests: `test_fr8701_*`, `test_fr9354_*`, `test_fr9468_*`.

## Fail-when

PriorityAgent.exe missing from bob-ear MSI stage / sha256 mismatch / `vendor/priority/PriorityAgent.exe` absent from stage.
