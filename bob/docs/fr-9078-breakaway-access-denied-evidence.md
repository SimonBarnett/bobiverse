# FR #9078 evidence

`BobTray.ConsoleLauncher.Start` (embedded in `Watch-BobTray.ps1`) retries `CreateProcessW` without `CREATE_BREAKAWAY_FROM_JOB` when the first attempt returns Win32 Access Denied (5).

## Why
Flamingo TipForm under schtasks job forbids breakaway; engine seat starts failed with `pid=0 launch-failed` until a live hotpatch added this retry.

## Notes
- Fallback seat stays in the parent job (weaker than FR #8568 breakaway).
- Compiled `WorkerLauncher.Launch` in `bob-tray.exe` is unchanged (follow-up FR).
- After sync, **Reload engine** / TipForm restart — `Add-Type` loads once per process.

## Tests
`python -m pytest -q bob/tests/test_fr8568_disappeared_seat_breakaway.py bob/tests/test_fr9078_breakaway_access_denied_fallback.py`
