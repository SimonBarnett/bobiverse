# BOB-55 / FR #8701 evidence: bob-ear MSI includes PriorityAgent.exe

**Issue:** https://github.com/SimonBarnett/bobiverse/issues/8701  
**Slice:** bob-ear MSI: include Priority exe (Success S1)

## S1

The bob product MSI stage includes ``priority\PriorityAgent.exe``.

## How measured

1. ``Stage-BobAgentFolders`` copies ``PriorityAgent.exe`` from ``BOB_PRIORITY_AGENT_EXE``, pack OutDir, or ``bob/tests/fixtures/PriorityAgent.exe``.
2. Marker ``priority\BOB-55-PRIORITY-IN-MSI.txt`` is written for heat harvest / MSI file list.
3. Production pack fails closed if the exe is missing (unless ``-SkipPriorityExe`` for test stage).

## Fail-when

PriorityAgent missing from bob-ear MSI layout.