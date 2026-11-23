# BOB-TRAY-UI-03 / FR #9263 — Workers Open Code Free|Paid

## Success S1

Workers > Open Code expands **Free** and **Paid** only (no model picker). Start uses the Weights / models webhook row (`Opencode-Free` / `Opencode`) with tray defaults as fallback.

## Surfaces

- TipForm `BobTray.cs` `AddOpencodeModelSubmenu` — labels Free / Paid; tooltip holds model id; click path already used `OpencodeWebhookModel` (FR #8732).
- Watch `Watch-BobTray.ps1` `Update-BobTrayWorkerAgentsMenu` — Open Code is a submenu with Free|Paid tags `opencode|free` / `opencode|paid` (was a flat single click).

## Evidence

```
pytest bob/tests/test_fr9263_opencode_free_paid_submenu.py bob/tests/test_fr6429_opencode_tray_submenu.py bob/tests/test_fr8732_opencode_webhook_model.py
```
