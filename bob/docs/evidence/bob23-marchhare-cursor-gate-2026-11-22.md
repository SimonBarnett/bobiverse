# BOB-23 / FR #8719 evidence: MarchHare Cursor token gate

**Date:** 2026-11-22  
**Acceptance S1:** Dialog + quit when MarchHare has no tokens. Fuel fixture MarchHare=0 (local may be 0); dialog shows. Fail-when: gates on local box only.

## Gate source

| Check | Path |
|-------|------|
| Meter | `fleet-cursor-private.json` (si@ntsa.uk / MarchHare) |
| Not used | Local `Get-BobTrayCursorFuelRemaining` / Spending |

## Surfaces

- C# tray `MarchHareCursorGate` before `WorkerLauncher.Launch` for `--agent cursor`
- PS tray `Test-BobTrayMarchHareCursorExhausted` in `Start-BobTrayWorkerExe` / Watch start
- `bob_worker` refuse → `show_out_of_fuel_dialog` + `EXIT_OUT_OF_FUEL`

## Offline proof

```text
python -m pytest bob/tests/test_fr8719_marchhare_cursor_gate.py bob/tests/test_fr8649_explicit_cursor_si_pool.py -q
```

Covers MarchHare=0 with local=0 and local>0; headless `--check-marchhare-cursor-gate`.

## Depends

BOB-21 (#8721) closed.
