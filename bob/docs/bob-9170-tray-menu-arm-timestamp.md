# TipForm menu arm timestamp (FR #9170)

## Problem
On live TipForm (`Watch-BobTray.ps1`), right-click armed the context menu by setting all items `Enabled=false` for a 350ms Forms.Timer. When the STA thread was blocked (Update-Hover / poll), that Timer starved — `MenuItemsArmed` arrived ~30s late and the menu looked grey/dead. Left-click while the strip was still `Visible` logged `StatusSkipped` / `tip show skipped reason=menu-open` and never showed the status card.

## Fix
- **Timestamp arm:** on `MenuOpened`, set `menuArmUntilUtc = UtcNow + 350ms`. Items stay `Enabled`. Exit ignores clicks inside that window (`Exit ignored reason=menu-arm-ts`). Never bulk `Enabled=false` on open.
- **Left-click dismiss:** if the strip is Visible (or `menuOpenSticky`), close it, log `StatusMenuDismiss`, then run Status / TipForm.
- **Park path:** `Invoke-BobTrayStatus` TipForm fallback calls `Show-BobTrayCard` without `Update-Hover` (paint from last poll; hover refresh stays on the engine timer).
- **Sticky clear:** `Show-BobTrayCard` clears `menuOpenSticky` when the menu is not Visible.

## Operator
After deploy, right-click should show live (non-grey) menu items immediately; left-click dismisses a stuck menu and parks the TipForm card.
