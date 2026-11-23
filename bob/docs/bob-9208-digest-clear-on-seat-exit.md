# FR #9208: digest doing after OpenCode seat process gone (RQ park-Watch-only)

## Problem
RedQueen TipForm is often `clickfalse-park` Watch-only. Compiled `bob-tray.exe` `ObserveWorkerSeats` / FR #8568 disappeared-seat GIVEUP does not run. When seats die (e.g. parent tray kill before FR #9205), digest can stay `doing`/`offered` while WinRM shows zero bob-worker processes.

## Fix
- `BobTrayObserveSeats.ps1`: Watch-side seat count + disappeared-run synthetic `last-exit.json` + shop `GIVEUP ... external-kill` (never restart seats)
- `Watch-BobTray.ps1` poll: call `Invoke-BobTrayObserveWorkerSeats` each engine cycle
- Jeeves monitor `opencode_seats.py`: default machines include `redqueen`; FR #9208 under-count finding when OpenCode seats less than `BOB_OPENCODE_EXPECT_SEATS` (default 2). Report-only.

## Ops
- Operator TipForm Agents starts replacement OpenCode seats
- Monitor must not Start-BobWorker / kill seats
- Prefer recovering Watch/TipForm so observe runs; empty-online.disabled stays

Related: FR #8568 compiled tray; FR #9205 seat-protect kill; FR #9199 intentional park.