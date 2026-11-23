"""FR #9154: TipForm ContextMenuStrip must not die on AppFocusChange.

bob-status / tip TOPMOST stole focus → MenuClosing reason=AppFocusChange.
Productize: cancel AppFocusChange; gate Status/tip while menu open; Opening
hides tip and closes bob-status; Status form ShowWithoutActivation.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import ROOT

WATCH = ROOT / "third_party" / "bob-tray" / "tools" / "Watch-BobTray.ps1"
STATUS_CS = ROOT / "third_party" / "bob-tray" / "dialogs" / "BobStatus.cs"
DOCS = ROOT / "docs" / "bob-9154-menu-appfocus-cancel.md"
WIN = pytest.mark.skipif(sys.platform != "win32", reason="tray PowerShell")


def test_fr9154_watch_pins_menu_focus_gate():
    t = WATCH.read_text(encoding="utf-8")
    assert "FR #9154" in t
    assert "function Test-BobTrayMenuShouldCancelClose" in t
    assert "$script:bobTrayMenuOpen" in t
    assert "$menu.Add_Opening" in t
    assert "$menu.Add_Closing" in t
    assert "$menu.Add_Closed" in t
    assert "AppFocusChange" in t
    assert "MenuClosingCancelled" in t
    assert "click-diag" in t
    status = t[t.index("function Invoke-BobTrayStatus") : t.index("function Invoke-BobTrayStatus") + 700]
    assert "bobTrayMenuOpen" in status
    show = t[t.index("function Show-BobTrayCard") : t.index("function Show-BobTrayCard") + 500]
    assert "bobTrayMenuOpen" in show
    assert "Hide-BobTrayCard" in t
    assert "CloseMainWindow" in t
    assert "bob-status" in t
    cancel = t[
        t.index("function Test-BobTrayMenuShouldCancelClose") : t.index(
            "function Test-BobTrayMenuShouldCancelClose"
        )
        + 450
    ]
    assert "AppFocusChange" in cancel

def test_fr9154_bob_status_show_without_activation():
    cs = STATUS_CS.read_text(encoding="utf-8")
    assert "ShowWithoutActivation" in cs
    assert "FR #9154" in cs
    assert "0x08000000" in cs or "WS_EX_NOACTIVATE" in cs


def test_fr9154_evidence_doc():
    assert DOCS.is_file()
    text = DOCS.read_text(encoding="utf-8")
    assert "FR #9154" in text
    assert "AppFocusChange" in text
    assert "MenuClosingCancelled" in text


@WIN
def test_fr9154_cancel_predicate_matches_watch(tmp_path: Path):
    t = WATCH.read_text(encoding="utf-8")
    start = t.index("function Test-BobTrayMenuShouldCancelClose")
    nxt = t.find("\nfunction ", start + 1)
    assert nxt > start
    excerpt = t[start:nxt]
    script = tmp_path / "c.ps1"
    script.write_text(
        excerpt
        + "\n"
        + "\n".join(
            [
                "$a = Test-BobTrayMenuShouldCancelClose -CloseReason 'AppFocusChange'",
                "$b = Test-BobTrayMenuShouldCancelClose -CloseReason 'ItemClicked'",
                "$c = Test-BobTrayMenuShouldCancelClose -CloseReason 'AppClickedOutside'",
                "$d = Test-BobTrayMenuShouldCancelClose -CloseReason 'Keyboard'",
                'Write-Output ("{0}|{1}|{2}|{3}" -f $a,$b,$c,$d)',
            ]
        )
        + "\n",
        encoding="utf-8-sig",
    )
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out
    assert "True|False|False|False" in out.replace("\r", "")
