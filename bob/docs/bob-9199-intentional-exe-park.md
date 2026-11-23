# FR #9199: intentional TipForm exe park (Watch-only)

## Problem
RedQueen keeps `tools\bob-tray.exe.clickfalse-park` so TipForm Watch owns the icon.
Sync / ForceNew / tray hotpatch / Ensure repeatedly re-drop `tools\bob-tray.exe` beside the park,
so live exe and Watch fight.

## Fix
- `Test-BobTrayIntentionalExeParkPresent` / `Remove-BobTrayLiveExeWhileParked` in `BobTrayLifecycle.ps1`
- `Restore-BobTrayExeFromClickfixPark` (FR #9044) refuses to revive live when intentional park is present
- `Get-BobSystrayTrayExe` returns null while parked (Start-BobFleetTray uses Watch-only)
- Sync, Install-BobTrayHotpatch, Ensure-BobTrayRunning strip live exe after refresh when parked

`bob-tray.exe.clickfix-park` alone still restores via FR #9044 (accidental missing live).