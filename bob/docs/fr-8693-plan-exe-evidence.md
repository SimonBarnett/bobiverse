# FR #8693 / BOB-44 evidence (updated FR #9271 / BOB-TRAY-UI-10)

Agents > Plan starts the vendored Plan seat exe.

- Path: `<install>\plan\PlanAgent.exe` (bob-ear MSI / BOB-49 / skills-visionary; FR #8833/#9354)
- Not: `bob-worker --mode plan`, not legacy `vendor\plan\bob-plan.exe`
- TipForm + Watch-BobTray both resolve that path; missing exe shows a dialog (no silent no-op)

`python -m pytest -q bob/tests/test_fr8693_plan_exe.py bob/tests/test_fr9271_plan_click_starts.py`
