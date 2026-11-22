# FR #8677 / BOB-09 evidence: About Show logs

## S1
About dialog has a bottom **Show logs** button that opens `%USERPROFILE%\.grok\long-running-background-tasks\watch_bob_tray.log` in Notepad (same path as tray menu **Open log**).

## Surfaces
- `bob/tray/dialogs/BobAbout.cs` — compiled AboutForm
- `bob/tray/tools/Watch-BobTray.ps1` — PowerShell About fallback
- Tests: `bob/tests/test_fr8677_about_show_logs.py`

## Out of scope
BOB-06 menu tree; renaming Open log menu item.
