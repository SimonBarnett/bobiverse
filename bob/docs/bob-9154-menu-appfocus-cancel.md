# TipForm ContextMenuStrip AppFocusChange (FR #9154)

## Problem
Park TipForm (`Watch-BobTray` NotifyIcon, FR #9011) opened the context menu then lost it. Click-diag on redqueen showed:

```
MouseDown Right → MenuOpening → MenuOpened → MouseUp → MouseClick Right
MenuClosing reason=AppFocusChange
```

Left-click Status launches `bob-status.exe` or in-process tip `ShowParkedAt` (HWND_TOPMOST). That steals focus; WinForms closes the strip with `ToolStripDropDownCloseReason.AppFocusChange`.

## Fix
1. `$script:bobTrayMenuOpen` with `MenuOpening` / `MenuClosed` (Opening also `Hide-BobTrayCard` + close `bob-status`).
2. `MenuClosing`: if reason is `AppFocusChange`, `$e.Cancel = $true` and log `MenuClosingCancelled` plus foreground hwnd/pid/name. ItemClicked / AppClickedOutside / Keyboard still close.
3. `Invoke-BobTrayStatus` / `Show-BobTrayCard` no-op while the menu is open.
4. `BobStatus` StatusForm: `ShowWithoutActivation` + `WS_EX_NOACTIVATE` (rebuild `bob-status.exe` via `Build-BobDialogs.ps1` to ship the exe).

## Manual check
- Right-click tray icon: menu stays open at least 5s without selecting an item.
- Status from the menu item still opens status after the menu closes.
- Left-click Status after the menu is closed still opens status.

## Related
FR #9011 park TipForm · #9149 STA Wait-Job freeze (separate)
