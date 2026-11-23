"""FR #9154 remnants: Status NOACTIVATE + click-diag (Cancel approach superseded by #9163).

Cancel AppFocusChange Closing stuck bobTrayMenuOpen (FR #9163). Keep BobStatus
ShowWithoutActivation and click-diag logging; menu close policy lives in #9163.
"""
from __future__ import annotations

from repo_layout import ROOT

WATCH = ROOT / "third_party" / "bob-tray" / "tools" / "Watch-BobTray.ps1"
STATUS_CS = ROOT / "third_party" / "bob-tray" / "dialogs" / "BobStatus.cs"
DOCS = ROOT / "docs" / "bob-9154-menu-appfocus-cancel.md"


def test_fr9154_bob_status_show_without_activation():
    cs = STATUS_CS.read_text(encoding="utf-8")
    assert "ShowWithoutActivation" in cs
    assert "FR #9154" in cs
    assert "0x08000000" in cs or "WS_EX_NOACTIVATE" in cs


def test_fr9154_click_diag_and_doc_point_to_9163():
    t = WATCH.read_text(encoding="utf-8")
    assert "click-diag" in t
    assert "MenuOpening" in t
    assert DOCS.is_file()
    text = DOCS.read_text(encoding="utf-8")
    assert "9163" in text
    assert "Cancel" in text
