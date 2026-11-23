# TipForm menuarm timestamp (FR #9171 / #9170)

## Problem (redqueen 2026-11-23 ~02:04Z)

Clicks reached NotifyIcon. Right-click opened the menu with all items `Enabled=false` for a 350ms WinForms Timer arm (`MenuItemsArmed`). When the STA poll blocked (`Update-Hover` / Wait-Job), the Timer starved — items stayed grey for ~30s. Left-click while the strip was `Visible` logged `StatusSkipped` / `tip skipped reason=menu-open`.

## Product

- Opening stamps `bobTrayMenuArmedAt` and leaves items **Enabled** (log `MenuItemsArmed`); no Enabled=false Timer
- `Test-BobTrayMenuArmReady` — Exit ignores clicks inside 350ms (`ExitArmIgnored`)
- `Invoke-BobTrayStatus`: dismiss stuck/visible menu (`StatusMenuDismiss`) then show the TipForm card
- Park / TipForm card path does not call `Update-Hover` before `Show-BobTrayCard` (card paints last poll)
- `Show-BobTrayCard` still clears sticky flag via `Clear-BobTrayMenuOpenIfHidden`

## Related

#9170 twin · #9163 never-Cancel · #9169 ghost heal · #9150 / #9149 TipForm STA poll · #9011 park
