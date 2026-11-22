# BOB TipForm NotifyIcon clicks (FR #9011)

## Problem
`bob-tray.exe` stayed alive in the interactive session while left/right-click on the NotifyIcon did nothing. Lifecycle showed `digest-fetch-failed`. ForceNew alone sometimes left a dead icon; TipForm via Watch-BobTray recovered clicks.

## Cause
`RefreshDigestPools` called `Process.WaitForExit(25000)` from the WinForms constructor, and the 15s Forms.Timer `Watchdog` ran WMI (`HealIrcBobIfIdle`) on the UI message pump. A blocked pump keeps the process up (`tray.alive` still ticks on a Threading.Timer) but Shell_NotifyIcon never delivers clicks.

## Fix
- Digest pool refresh starts on a `System.Threading.Timer` with dueTime 0 (no sync ctor WaitForExit).
- Overlapping digest refreshes skip via Interlocked `digestPoolsBusy`.
- Watchdog Tick only queues ThreadPool work (`QueueWatchdog`); WMI/heal never owns the pump.

## Operator
After hotpatching `bob-tray.exe`, use TipForm **Restart** or `Start-BobFleetTray -ForceNew -SkipServiceRestart` (tidy still clears orphan icons). Do not kill OpenCode seats; do not restart ircBob.
