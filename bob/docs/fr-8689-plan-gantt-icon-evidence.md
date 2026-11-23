# FR #8689 / BOB-48 evidence

Agents > Plan uses the Plan GANTT asset from skills-visionary, not a generic icon.

- Source: `SimonBarnett/skills-visionary` `apps/plan_agent/assets/plan-gantt.ico` and `plan-gantt.png` (VIS-06).
- Tray file: `bob/tray/assets/plan-gantt.ico`
- Compiled log: `%LOCALAPPDATA%\Bobiverse\tray-lifecycle.log` event `plan` action `gantt icon` path `<install>\bob\tray\assets\plan-gantt.ico`
- PowerShell log: `Plan: GANTT icon <bob\tray>\assets\plan-gantt.ico`
- Docs: `jeeves/www/irc-ntsa/docs/tray/index.html` image `plan-gantt.png` (same bytes as the tray PNG).

`python -m pytest -q bob/tests/test_fr8689_plan_gantt_icon.py`
