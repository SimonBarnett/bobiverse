# bob-status windowless single-instance (FR #9165)

## Problem (redqueen 2026-11-23)
After menustuck revert, TipForm left-click looked dead for two stacked reasons:
1. Ghost NotifyIcon (prior Watch pid) — ops: Clear-BobOrphanNotifyIcons + relaunch.
2. **Windowless `bob-status.exe`** held the single-instance mutex with `MainWindowHandle=0`. `Start-BobTrayDialog` returned success; further left-clicks did nothing. Right-click menu still worked.

## Fix
- `BobDialogsCommon.AbandonSingle` + `BobStatus` Main: if HWND is zero after construct, abandon mutex and exit 2 (rebuild `bob-status.exe` to ship).
- `Start-BobTrayDialog -Name status`: wait up to 2s for a non-zero `MainWindowHandle`; kill windowless processes; return `$false` so TipForm card paints.
- While `tools\bob-tray.exe.click{false,true,fix}-park` exists, skip bob-status and use `Show-BobTrayCard`.
- Keep `Show-BobTrayCard` with `param()` as the first statement.

## Manual check
- With park present: left-click shows TipForm card.
- Without park: left-click either shows bob-status HWND or falls back to TipForm (never silent).
- Right-click menu still arms after ~350ms (FR #9163).

## Related
#9163 menustuck · #9154 · #9011 · #9044 clickfix-park
