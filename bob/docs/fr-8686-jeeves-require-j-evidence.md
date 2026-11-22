# FR #8686 / BOB-36 evidence

Agents > Jeeves requires a J: map. A missing map shows a dialog and quits the start. It does not launch `bob-worker --mode agent --agent grok`.

- Compiled tray: `JeevesJDrivePresent(@"J:\")` then `action` `J: map missing` and `return` before `StartWorker`.
- PowerShell tray: `Test-BobTrayJeevesDrive` then `Jeeves: J: map missing; quit` and `return` before `Start-BobTrayWorkerExe`.
- Missing-path fixture returns false. An existing directory returns true.

`python -m pytest -q bob/tests/test_fr8686_jeeves_require_j.py`
