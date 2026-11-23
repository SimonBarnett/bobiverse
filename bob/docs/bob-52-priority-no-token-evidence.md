# BOB-52 / FR #8698 evidence: Priority no-token dialog + quit

**Slice:** Agents > Priority: no-token dialog + quit (Success S1)

## S1

When this box's Priority fuel file is known-empty, the tray shows a no-token dialog and **quits** the start (does not launch `PriorityAgent.exe`). The tray process stays running.

| Case | Fuel file | Result |
|------|-----------|--------|
| Fuel-empty fixture | `remaining_pct` 0 / `status` empty | Dialog + quit; no start |
| Fuel-ok fixture | positive remaining | Allow start |
| Missing file | (absent) | Allow start (unknown; PriorityAgent applies its own check) |

## How measured

- Fixtures: `bob/tests/fixtures/priority-fuel-empty.json`, `priority-fuel-ok.json`
- Tests: `bob/tests/test_fr8698_priority_no_token.py`
- Env override: `BOB_PRIORITY_FUEL_FILE`
- Default path: `%LOCALAPPDATA%\Bobiverse\priority-fuel.json`

## Surface

- Compiled: `BobTray.cs` `PriorityFuelEmpty` before `StartPriorityExe` on **Start PriorityAgent**
- Fallback: `Watch-BobTray.ps1` `Test-BobTrayPriorityFuelEmpty` before `Start-BobTrayPriorityExe`

## Out of scope

- Digest `xai_weekly` reconciliation (tray Status already owns that contract)
- Changes inside `priority-mcp` / `PriorityAgent.exe`
- Blocking on unknown/stale fuel
