# BOB-52 / FR #8698 evidence: Priority no-token dialog + quit

**Issue:** https://github.com/SimonBarnett/bobiverse/issues/8698  
**Slice:** Agents > Priority: no-token dialog + quit (Success S1)

## S1

This-box no-token gate: when Priority fuel is empty, show dialog and **quit** (do not start).

## How measured

Fuel-empty fixture (`BOB_PRIORITY_FUEL_REMAINING=0` or JSON fixture with `"remaining": 0`):

1. `Invoke-BobPriorityNoTokenGate -NoUi` / `Start-BobTrayPriorityAgent -NoUi` returns `AllowStart=false`, `Quit=true`.
2. Log `%LOCALAPPDATA%\Bobiverse\logs\priority-no-token-gate.log` cites `dialog=no-tokens`, `quit=true`, `start=blocked`.

## Fail-when

Starts without tokens (gate returns allow on remaining <= 0).

## Depends-on

BOB-50 owns PriorityAgent.exe start; this slice only gates empty fuel.