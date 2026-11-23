# FR #8699 / BOB-50 evidence

Agents > Priority starts `<install>\vendor\priority\PriorityAgent.exe`.

- Compiled tray log: `%LOCALAPPDATA%\Bobiverse\tray-lifecycle.log` event `priority` action `start exe` with that path.
- PowerShell tray log: `Priority: start exe <path>`. A missing exe is logged and the click returns.

`python -m pytest -q bob/tests/test_fr8699_priority_exe.py`
