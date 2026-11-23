# FR #8733 / BOB-28 evidence

Workers > Open Code: when the fuel fixture has free=0 and paid/go=0, the tray shows a dialog and does not start an OpenCode seat.

- Gate: `bob/tray/dialogs/OpenCodePaidExhaustedGate.cs` (`IsExhaustedDocument` / `ShouldQuit`).
- Compiled tray: `StartWorker` for agent `opencode` returns after MessageBox; lifecycle `workers-opencode` action `dialog-quit` reason `paid-exhausted`.
- PowerShell tray: `Test-BobTrayOpenCodePaidExhausted` + `Show-BobTrayOpenCodePaidExhaustedDialog` before Workers Open Code start.
- Headless: `bob-tray.exe --check-opencode-paid-exhausted <out.json>` exit 2 when exhausted, 0 otherwise.
- Doc: `bob/docs/bob-28-opencode-paid-exhausted.md`.

`python -m pytest -q bob/tests/test_fr8733_workers_opencode_paid_exhausted.py`
