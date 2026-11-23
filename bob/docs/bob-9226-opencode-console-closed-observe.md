# FR #9226: OpenCode console vanish without seat-exit / GIVEUP

## Problem
TipForm-started OpenCode seats on flamingo hung then consoles vanished (`0 opencode.exe`, only Grok seats left). Historical OC runs already recorded `last-exit.json` with `reason=console-closed` / `exit_code=3221225786` when bob-worker reached `shutdown`. Live gap: after a hard death or tray restart, Watch/`ObserveWorkerSeats` only healed disappeared run dirs when the **seat count dropped**. A restart that baselines on remaining Grok seats never scanned orphan OC run dirs, so digest could lag and `tray-lifecycle.log` had no fresh `seat-exit` / `seat-disappeared` with a clear reason.

## Fix
- `BobTrayObserveSeats.ps1` / compiled `BobTray.cs`: **always** call disappeared-run heal each poll; classify `console-closed` vs `external-kill` from `worker.log` (CTRL_CLOSE / `0xC000013A` / `3221225786`); GIVEUP with that reason; lifecycle fields include `nick`, `reason`, `exit_code`.
- `bob_worker.classify_disappeared_seat_reason` + `handle_disappeared_worker_run` mirror the same classification.
- Never auto-restart seats (operator TipForm Agents).

## Ops
- Operator starts replacement OpenCode seats when ready.
- Monitor stays report-only (`opencode_seats` under-count).
- Related: FR #9208 Watch observe, FR #9205 tray seat-protect, FR #8154 console-closed GIVEUP, FR #8568 disappeared seat.
