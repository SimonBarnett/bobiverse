# FR #9097 evidence

Compiled-menu `WorkerLauncher.Launch` (`bob/tray/dialogs/BobTray.cs`) retries `CreateProcessW` without `CreateBreakawayFromJob` when Win32 returns Access Denied (5).

## Pairing
Companion to FR #9078 (PowerShell `BobTray.ConsoleLauncher` in `Watch-BobTray.ps1`).

## Deploy note
Source lands in-repo; compiled-menu clicks need an authorised `bob-tray.exe` rebuild (bob/AGENTS.md). This FR does not bump VERSION or release.

## Tests
`python -m pytest -q bob/tests/test_fr9097_workerlauncher_breakaway_fallback.py bob/tests/test_fr8568_disappeared_seat_breakaway.py`
