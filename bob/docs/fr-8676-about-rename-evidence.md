# FR #8676 / BOB-08 evidence: About rename

## S1
Tray context-menu label **Acknowledge** renamed to **About** (matches `bob/docs/mocks/systray-agents-workers/home.html`).

## Surfaces
- `bob/tray/dialogs/BobTray.cs` — compiled menu `Item("About", ...)` (attention clear via `Acknowledge()` unchanged)
- `bob/tray/tools/Watch-BobTray.ps1` — PowerShell fallback `$menu.Items.Add('About')`
- `bob/docs/bob-tray-dialogs.md` — menu prose
- Tests: `bob/tests/test_fr8676_about_menu_label.py`, `bob/tests/test_tray_dialogs_828.py` menu dump

## Out of scope
Full BOB-06 menu tree (Agents/Workers/Weights nesting); attention-clear handler rename.
