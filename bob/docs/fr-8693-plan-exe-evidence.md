# FR #8693 / BOB-44 evidence (updated FR #9271 / BOB-TRAY-UI-10 / FR #9605)

Agents > Plan starts the vendored Plan seat exe.

- Path: `<install>\vendor\plan\PlanAgent.exe` (Pack/Sync mirror of MSI `plan\PlanAgent.exe`; FR #9468/#9598/#9605)
- Not: `bob-worker --mode plan`, not legacy `vendor\plan\bob-plan.exe`, not TipForm dependency on `plan\PlanAgent.exe`
- TipForm + Watch-BobTray both resolve that path; missing exe shows a dialog naming `vendor\plan\PlanAgent.exe` (no silent no-op)

`python -m pytest -q bob/tests/test_fr8693_plan_exe.py bob/tests/test_fr9271_plan_click_starts.py bob/tests/test_fr9605_plan_starts_vendor_planagent.py`

## FR #9641
Agents > Plan remains `StartPlanExe` -> `vendor\plan\PlanAgent.exe`; Pack `Assert-BobiversePlanAgentNotBobWorker` refuses identical bob-worker bytes under PlanAgent.

