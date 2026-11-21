# BOB-07 / FR #8706 evidence: Exit submenu Reload / Restart engine / Exit

**Issue:** https://github.com/SimonBarnett/bobiverse/issues/8706
**Slice:** Exit submenu: Reload / Restart engine / Exit (Success S1)
**Depends-on:** BOB-06 (soft; this slice only nests Exit actions)

## S1

Reload, Restart engine, and Exit live under the Exit submenu only (not top-level).

## How measured

1. `bob/tray/dialogs/BobTray.cs` builds `ToolStripMenuItem("Exit")` with DropDownItems Reload, Restart engine, Exit (leaf).
2. `bob/tray/tools/Watch-BobTray.ps1` TipForm mirrors the same Exit submenu.
3. `--dump-menu` / `test_tray_dialogs_828` expects Exit then Reload / Restart engine / Exit (no top-level Restart or Reload engine).
4. Tests: `bob/tests/test_fr8706_exit_submenu.py`.

## Fail-when

Actions still top-level only (`Item("Restart")` / `Item("Reload engine")` / `Item("Exit")`).
