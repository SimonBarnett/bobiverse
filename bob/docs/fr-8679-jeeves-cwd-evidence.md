# FR #8679 / BOB-37 evidence

Agents > Jeeves starts the Grok seat with cwd `J:\` (the drive mapped to Ergo `ai\jeeves`).

Dry-run / tray log prints `cwd J:` before start.

- Compiled tray: `TrayLifecycle.Write("jeeves", "cwd", "cwd J:")` then `StartWorker(..., @"J:\")`.
- PowerShell tray: `Write-TrayLog 'cwd J:'` and `Start-BobTrayWorkerExe -Trigger 'jeeves-menu'` forces `$wd = 'J:\'`.

`python -m pytest -q bob/tests/test_fr8679_jeeves_cwd.py`
