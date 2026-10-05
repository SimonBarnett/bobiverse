"""FR #2590: BobTrayDialogs Start-Process --root must not embed quotes in argv."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

DIALOGS = ROOT / "bob" / "tray" / "tools" / "BobTrayDialogs.ps1"
FLEET = ROOT / "bob" / "tray" / "tools" / "Start-BobFleetTray.ps1"


def test_fr2590_dialogs_start_process_root_unquoted():
    t = DIALOGS.read_text(encoding="utf-8-sig")
    assert "Start-BobTrayDialog" in t
    assert "@('--root', $Root)" in t or '@("--root", $Root)' in t
    # Footgun from FR #2585 must not remain in Dialogs helper.
    assert "('{0}\"'" not in t.replace(" ", "")
    assert "('--root', ('\"{0}\"' -f $Root))" not in t
    assert "FR #2590" in t or "FR #2585" in t


def test_fr2590_fleet_still_unquoted_after_2585():
    t = FLEET.read_text(encoding="utf-8-sig")
    assert "@('--root', $RepoRoot)" in t or '@("--root", $RepoRoot)' in t
