# TipForm sticky menu-open / ghost icon (FR #9163)

## Problem (redqueen 2026-11-23)
1. Hotpatch cancelled `ContextMenuStrip` Closing on `AppFocusChange` → `Closed` never fired → sticky `$script:bobTrayMenuOpen=true` with an invisible strip → left-click logged `status skipped: menu open` (icon remains, no click).
2. After revert, clicks sometimes hit a **ghost** Shell_NotifyIcon from a prior Watch pid (Clear-BobOrphanNotifyIcons alone is weak; explorer recycle in the interactive session may be needed).

## Product rule
**Never Cancel** Closing on TipForm ContextMenuStrip for `AppFocusChange` (or any reason): do not set `$e.Cancel = $true`. Prefer:
- Delay-enable menu items (~350ms) after Opening (`MenuItemsArmed`)
- Clear sticky `$script:bobTrayMenuOpen` when the menu is not `Visible` (`MenuFlagCleared`) before Status/tip
- Opening still hides tip and closes `bob-status`
- Exit asks Yes/No so a focus-steal ItemClicked does not kill Watch
- Keep click-diag; BobStatus `ShowWithoutActivation` (FR #9154) still helps

## Operator
Right-click the **newest** robot icon. If clicks stay dead: prefer `Clear-BobOrphanNotifyIcons.ps1 -HealLadder` (FR #9169: explorer recycle when toolbars=0), then relaunch Watch. Park `bob-tray.exe.clickfix-park` and ircBob stay up.

## Related
#9154 (Cancel approach superseded) · #9169 ghost heal · #9011 · #9149 · `Clear-BobOrphanNotifyIcons.ps1`
