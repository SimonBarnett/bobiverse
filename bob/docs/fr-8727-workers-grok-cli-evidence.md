# FR #8727 / BOB-16 evidence

Workers > Grok starts the Grok CLI seat (`bob-worker.exe --mode agent --agent grok`) and the log names grok.

- Compiled tray: `%LOCALAPPDATA%\Bobiverse\tray-lifecycle.log` event `workers-grok` action `grok CLI start`.
- PowerShell tray log: `Workers Grok: grok CLI start`, trigger `workers-grok`.

`python -m pytest -q bob/tests/test_fr8727_workers_grok_cli.py`
