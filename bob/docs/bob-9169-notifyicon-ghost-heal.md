# TipForm ghost/dead NotifyIcon heal (FR #9169)

## Problem (redqueen 2026-11-23 ~01:58Z)

Watch stayed Running/polling with **zero MouseDown after MenuClosed** while the operator clicked a dead prior Shell_NotifyIcon. `Clear-BobOrphanNotifyIcons` reported `toolbars=0` / `mousePosts=0` (Win11 notify chrome often has no classic `ToolbarWindow32` under `SysPager`), so the WM_MOUSEMOVE sweep was a no-op.

Ops heal ladder that restored clicks:

1. Kill live Watch
2. Clear-BobOrphanNotifyIcons
3. Recycle `explorer.exe` in the interactive session (e.g. PsExec `-i 3`)
4. Clear again
5. Relaunch Watch

Park and ircBob stayed up.

## Product

- `Clear-BobOrphanNotifyIcons.ps1`: broader child enum (`ToolbarWindow32` + `DirectUIHWND`); `-HealLadder` recycles explorer in the **current** session when the first pass finds `toolbars=0`, then re-sweeps; `-RecycleExplorer` forces recycle; refuses session 0; JSON adds `explorerRecycled` / `recycleReason` / `toolbarsBefore`.
- `Start-BobFleetTray` tidy + post-start sweep pass `-HealLadder`.
- TipForm `MenuClosed`: soft rebind (`Visible=$false` then `$true`) and log `NotifyIconRebound` so a live dead registration recovers before ops need explorer recycle.

## Operator

Right-click the **newest** robot icon. If clicks stay dead after MenuClosed:

```text
powershell -NoProfile -File <install>\tools\Clear-BobOrphanNotifyIcons.ps1 -HealLadder
```

Then relaunch Watch (`Start-BobFleetTray` / tray Restart). Prefer HealLadder over a bare Clear when prior runs logged `toolbars=0`.

## Related

#9165 windowless bob-status · #9163 never-Cancel menustuck · #9166 twin path (HWND + menustuck) · #9011 pump · `Clear-BobOrphanNotifyIcons.ps1`
