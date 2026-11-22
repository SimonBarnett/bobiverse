# FR #8688 / BOB-33 evidence

Agents > Jeeves starts a Grok seat (`bob-worker.exe --mode agent --agent grok`).

- Compiled tray: `TrayLifecycle.Write` event `jeeves` with `action=grok start` in `%LOCALAPPDATA%\Bobiverse\tray-lifecycle.log`, then `StartWorker("agent", "grok")`.
- PowerShell tray: `Write-TrayLog 'Jeeves: grok start'` then `Start-BobTrayWorkerExe -Mode agent -Agent grok -Trigger jeeves-menu`.

`python -m pytest -q bob/tests/test_fr8688_jeeves_grok_start.py`
