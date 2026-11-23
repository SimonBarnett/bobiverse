# FR #9205: re-park must not kill TipForm OpenCode seats

## Problem
On RedQueen TipForm is Watch-only (`bob-tray.exe.clickfalse-park`). Staging sometimes re-drops live `bob-tray.exe`. Ops/Ensure then `Stop-Process bob-tray` while that PID (or Watch) is **parent of bob-worker wrappers**. Seats die with lifecycle `seat-exit via=bob-tray-watchdog was=N now=0`.

## Fix
- `Test-BobTrayProcessHasSeatChildren` / `Stop-BobTrayProcessesProtectingSeats` in `BobTrayLifecycle.ps1`
- Ensure park strip (FR #9199): remove live exe; kill bob-tray only when it has **no** seat children
- `Start-BobFleetTray -ForceNew`: skip kill for tray/Watch PIDs that parent seats

## Ops
While operator OpenCode seats are doing on RQ:
- Prefer **file delete** of staged `tools\bob-tray.exe` when the process is not running
- Do **not** `Stop-Process bob-tray` (or kill Watch) unless seats are reparented / finished
- If the live exe is locked by a running parent of seats, leave the process; quarantine/delete staging copies only

Related: FR #9199 intentional park; FR #9078/#9097 CREATE_BREAKAWAY_FROM_JOB (Access Denied leaves seats in parent job).