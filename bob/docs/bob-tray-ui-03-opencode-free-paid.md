# BOB-TRAY-UI-03 / FR #9263 → FR #9588 — Workers OpenCode Free|Paid top-level

## Success S1

Workers menu shows sibling rows **OpenCode Free** and **OpenCode Paid** (no Open Code parent submenu; no model picker). Start uses the Weights / models webhook row (`Opencode-Free` / `Opencode`) with tray defaults as fallback. Tags stay `opencode|free` / `opencode|paid`.

## Surfaces

- TipForm `BobTray.cs` `AddOpencodeTopLevelChoices` — labels OpenCode Free / OpenCode Paid; tooltip holds model id; click path uses `OpencodeWebhookModel` (FR #8732).
- Watch `Watch-BobTray.ps1` `Update-BobTrayWorkerAgentsMenu` — expands the list-agents `opencode` row into two top-level items with the same tags (FR #9588; was FR #9263 submenu).

## Evidence

```
pytest bob/tests/test_fr9588_opencode_toplevel.py bob/tests/test_fr9263_opencode_free_paid_submenu.py bob/tests/test_fr6429_opencode_tray_submenu.py bob/tests/test_fr8732_opencode_webhook_model.py
```
