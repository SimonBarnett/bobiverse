# TipForm poll: no Wait-Job update-hover (FR #9150 / #9149)

## Problem

Deterministic exception `Watch-BobTray.engine-step.update-hover` with `timeoutSec=8` on RedQueen TipForm (#9011 park): the WinForms STA poll used `Invoke-BobTrayEngineStep` (`Wait-Job`) for `update-hover`, then called `Update-Hover` again (second `Get-BobTrayHover`). Combined with UI `worker-sync` and `Write-BobIrcStatus`, right-click ContextMenuStrip froze for tens of seconds (#9149). Cap-at-8s hotpatch still filed #9150 timeouts.

## Product

TipForm poll (`-not engine`):

- `step-skip name=worker-sync reason=tipform-ui-threadpool` — `trayWorkerSyncTimer` owns sync
- `step-skip name=update-hover reason=tipform-ui-snapshot` — no STA `Wait-Job`; `trayHoverTimer` writes `run\tray-status.json`
- `Update-Hover -FromSnapshot` paints NotifyIcon/tip from the snapshot only
- `step-skip name=digest-status reason=tipform-ui-threadpool` — `trayDigestTimer` posts for TipForm and engine

Engine mode keeps `update-hover-engine` warm step unchanged.

## Related

#9149 TipForm STA freeze · #9011 park · #7579 / #8518 engine steps · #4142 / #1553 ThreadPool timers · #9150 exception receipt
