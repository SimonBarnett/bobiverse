# FR #8693 / BOB-44 evidence

Agents > Plan starts the vendored Plan exe.

- Path: `<install>\vendor\plan\bob-plan.exe`
- Compiled tray log: `%LOCALAPPDATA%\Bobiverse\tray-lifecycle.log` event `plan` action `start exe` with that path.
- PowerShell tray log: `Plan: start exe <path>`. Missing exe is logged and does not fall back to `bob-worker --mode plan`.

`python -m pytest -q bob/tests/test_fr8693_plan_exe.py`
