# -*- coding: utf-8 -*-
"""FR #9166: bob-status release mutex without HWND; TipForm fallback; park; menustuck."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

DIALOGS = ROOT / "bob" / "tray" / "dialogs"
TRAY_TOOLS = ROOT / "bob" / "tray" / "tools"
COMMON_CS = DIALOGS / "BobDialogsCommon.cs"
STATUS_CS = DIALOGS / "BobStatus.cs"
DIALOGS_PS1 = TRAY_TOOLS / "BobTrayDialogs.ps1"
WATCH = TRAY_TOOLS / "Watch-BobTray.ps1"


def test_fr9166_common_releases_single_mutex():
    t = COMMON_CS.read_text(encoding="utf-8-sig")
    assert "ReleaseSingle" in t
    assert "keep.ReleaseMutex" in t or "ReleaseMutex()" in t


def test_fr9166_status_exits_without_visible_hwnd():
    t = STATUS_CS.read_text(encoding="utf-8-sig")
    assert "ReleaseSingle" in t
    assert "IsHandleCreated" in t or "MainWindowHandle" in t or "Handle ==" in t or "Handle==" in t
    # Must not keep mutex when windowless (FR #9166).
    assert "visible" in t.lower() or "Handle" in t


def test_fr9166_start_dialog_probes_hwnd_and_falls_back():
    t = DIALOGS_PS1.read_text(encoding="utf-8-sig")
    assert "function Start-BobTrayDialog" in t
    fn = t[t.find("function Start-BobTrayDialog") : t.find("function Start-BobTrayDialog") + 2500]
    assert "MainWindowHandle" in fn
    assert "Stop-Process" in fn or "Kill" in fn
    assert "PassThru" in fn


def test_fr9166_invoke_status_park_skips_bob_status():
    t = WATCH.read_text(encoding="utf-8-sig")
    assert "function Invoke-BobTrayStatus" in t
    fn = t[t.find("function Invoke-BobTrayStatus") : t.find("function Invoke-BobTrayStatus") + 1800]
    assert "clickfalse-park" in fn or "clicktrue-park" in fn
    assert "Show-BobTrayCard" in fn


def test_fr9166_menustuck_never_cancels_appfocuschange():
    t = WATCH.read_text(encoding="utf-8-sig")
    assert "MenuItemsArmed" in t or "350" in t
    assert "MenuFlagCleared" in t or "bobTrayMenuOpen" in t
    # Must not productize the bad Cancel path for AppFocusChange.
    closing = ""
    if "Add_Closing" in t:
        idx = t.find("Add_Closing")
        closing = t[idx : idx + 800]
    assert "Cancel = $true" not in closing
    assert "e.Cancel = $true" not in closing or "AppFocusChange" not in closing
    # Explicit never-cancel note preferred
    assert "AppFocusChange" in t
    assert "never Cancel" in t.lower() or "Never Cancel" in t or "do not Cancel" in t.lower() or "Cancel AppFocusChange" in t


def test_fr9166_show_bob_tray_card_param_first():
    t = WATCH.read_text(encoding="utf-8-sig")
    idx = t.find("function Show-BobTrayCard")
    assert idx > 0
    chunk = t[idx : idx + 200]
    # param() must be the first statement in the function body
    assert "param(" in chunk
    before_param = chunk.split("param(", 1)[0]
    # After the function line, only whitespace/comments before param
    body = before_param.split("{", 1)[-1]
    assert body.strip() == "" or body.strip().startswith("#")
