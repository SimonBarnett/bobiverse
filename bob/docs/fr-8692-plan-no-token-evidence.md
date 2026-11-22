# FR #8692 / BOB-46 evidence

Agents > Plan shows a dialog and quits when this box has no tokens. It does not start `vendor\plan\bob-plan.exe`.

- Fuel file: `%LOCALAPPDATA%\Bobiverse\plan-fuel.json`, or `BOB_PLAN_FUEL_FILE`.
- Empty means `remaining_pct` <= 0 or status `empty` / `exhausted` / `out-of-fuel`. A missing file does not block.
- Fixture: `bob/tests/fixtures/plan-fuel-empty.json`.
- Compiled log: event `plan` action `no tokens` quit `1`.
- PowerShell log: `Plan: no tokens; quit`.

`python -m pytest -q bob/tests/test_fr8692_plan_no_token.py`
