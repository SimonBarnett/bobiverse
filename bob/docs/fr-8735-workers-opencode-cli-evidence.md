# FR #8735 / BOB-26 evidence

Workers > Open Code starts the OpenCode CLI seat (`bob-worker.exe --mode agent --agent opencode`) and the log names opencode.

- Compiled tray: `%LOCALAPPDATA%\Bobiverse\tray-lifecycle.log` event `workers-opencode` action `opencode CLI start`.
- PowerShell tray log: `Workers Open Code: opencode CLI start`, trigger `workers-opencode`.

`python -m pytest -q bob/tests/test_fr8735_workers_opencode_cli.py`
