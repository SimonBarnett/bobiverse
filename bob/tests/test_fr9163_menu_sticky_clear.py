"""FR #9163: never Cancel AppFocusChange Closing; clear sticky menu-open flag.

Cancel AppFocusChange left Closed unfired → sticky bobTrayMenuOpen with an
invisible strip → left-click StatusSkipped (icon remains, no click). Prefer
delay-enable menu items (~350ms) and clear the sticky flag when menu !Visible.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import ROOT

WATCH = ROOT / "third_party" / "bob-tray" / "tools" / "Watch-BobTray.ps1"
DOCS_9163 = ROOT / "docs" / "bob-9163-menu-sticky-clear.md"
DOCS_9154 = ROOT / "docs" / "bob-9154-menu-appfocus-cancel.md"
WIN = pytest.mark.skipif(sys.platform != "win32", reason="tray PowerShell")


def test_fr9163_never_cancel_appfocus_closing():
    t = WATCH.read_text(encoding="utf-8")
    assert "FR #9163" in t
    assert "MenuItemsArmed" in t
    assert "MenuFlagCleared" in t
    assert "function Clear-BobTrayMenuOpenIfHidden" in t
    assert "function Set-BobTrayMenuItemsEnabled" in t
    # Must not Cancel Closing for AppFocusChange anymore.
    assert "MenuClosingCancelled" not in t
    assert "$e.Cancel = $true" not in t
    assert "Test-BobTrayMenuShouldCancelClose" not in t
    assert "350" in t
    # Sticky clear before status gate
    status = t[t.index("function Invoke-BobTrayStatus") : t.index("function Invoke-BobTrayStatus") + 900]
    assert "Clear-BobTrayMenuOpenIfHidden" in status
    assert "bobTrayMenuOpen" in status
    # Opening still cleans tip/status windows
    assert "Hide-BobTrayCard" in t
    assert "Close-BobTrayStatusWindows" in t
    assert "click-diag" in t


def test_fr9163_evidence_and_9154_doc_updated():
    assert DOCS_9163.is_file()
    text = DOCS_9163.read_text(encoding="utf-8")
    assert "FR #9163" in text
    assert "never Cancel" in text.lower() or "Never Cancel" in text
    assert "MenuFlagCleared" in text
    assert "MenuItemsArmed" in text
    # 9154 doc must point at the correction
    d9154 = DOCS_9154.read_text(encoding="utf-8")
    assert "9163" in d9154
    assert "Cancel" in d9154


@WIN
def test_fr9163_clear_sticky_when_not_visible(tmp_path: Path):
    t = WATCH.read_text(encoding="utf-8")
    start = t.index("function Clear-BobTrayMenuOpenIfHidden")
    nxt = t.find("\nfunction ", start + 1)
    excerpt = t[start:nxt]
    script = tmp_path / "c.ps1"
    script.write_text(
        "function Write-TrayLog { param($m) }\n"
        + excerpt
        + "\n"
        + "\n".join(
            [
                "$script:bobTrayMenuOpen = $true",
                "$menu = [pscustomobject]@{ Visible = $false }",
                "$cleared = Clear-BobTrayMenuOpenIfHidden -Menu $menu",
                'Write-Output ("{0}|{1}" -f $cleared, $script:bobTrayMenuOpen)',
                "$script:bobTrayMenuOpen = $true",
                "$menu2 = [pscustomobject]@{ Visible = $true }",
                "$cleared2 = Clear-BobTrayMenuOpenIfHidden -Menu $menu2",
                'Write-Output ("{0}|{1}" -f $cleared2, $script:bobTrayMenuOpen)',
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
    out = ((r.stdout or "") + (r.stderr or "")).replace("\r", "")
    assert r.returncode == 0, out
    assert "True|False" in out
    assert "False|True" in out
