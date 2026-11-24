# BOB-07 / FR #8706 evidence: Exit submenu Restart / Reload Engine / Exit

**Issue:** https://github.com/SimonBarnett/bobiverse/issues/8706
**Slice:** Exit submenu: Restart / Reload Engine / --- / Exit (Success S1; operator 2026-11-24)
**Depends-on:** #9584 (unheld fr-digest); BOB-06 soft

## S1

Restart, Reload Engine, and Exit live under the Exit submenu only (not top-level).
Separator between Reload Engine and Exit leaf.

## Label-to-handler mapping

| Label | Host (BobTray.cs) | TipForm (Watch-BobTray.ps1) |
| --- | --- | --- |
| Restart | `Restart()` host relaunch | `Restart-BobTrayWatcher` |
| Reload Engine | `ReloadEngine()` | write `tray-cmd.txt` `reload` |
| Exit (leaf) | `ExitTray()` | confirm + `Invoke-BobTrayExit` |

Parent Exit has no Click handler (opens submenu only). PowerShell fallback nesting is out of scope.

## How measured

1. `bob/tray/dialogs/BobTray.cs` builds Exit DropDownItems: Restart, Reload Engine, separator, Exit.
2. TipForm mirrors the same tree.
3. `--dump-menu` / `test_tray_dialogs_828` expects Exit then Restart / Reload Engine / - / Exit.
4. Tests: `bob/tests/test_fr8706_exit_submenu.py`.

## Fail-when

Actions still top-level only (`Item("Restart")` / `Item("Reload engine")` / `Item("Exit")`).
