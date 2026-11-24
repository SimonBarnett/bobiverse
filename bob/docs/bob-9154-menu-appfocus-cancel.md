# TipForm ContextMenuStrip AppFocusChange (FR #9154) — superseded by #9163

## Original problem
Park TipForm context menu closed with `MenuClosing reason=AppFocusChange` when `bob-status` / tip TOPMOST stole focus.

## Wrong fix (do not ship)
Cancelling Closing on `AppFocusChange` left `Closed` unfired → sticky `$script:bobTrayMenuOpen=true` → left-click Status skipped (FR #9163 evidence on redqueen).

## Corrected approach
See `bob-9163-menu-sticky-clear.md`: never Cancel Closing; delay-arm menu items; clear sticky flag when menu `!Visible`; keep Opening tip/`bob-status` cleanup; BobStatus `ShowWithoutActivation` + `WS_EX_NOACTIVATE` remains useful (rebuild `bob-status.exe` to ship).

## Related
FR #9163 · #9011 · #9149
