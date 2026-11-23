"""FR #9171 / #9170: TipForm menu arm via timestamp (items stay Enabled).

Enabled=false + WinForms Timer starved when STA blocked → grey dead menu for
~30s; left-click then StatusSkipped. Productize RQ hotpatch: stamp arm time,
keep items Enabled, Exit ignores clicks inside 350ms; left-click dismisses
stuck menu then shows card; park TipForm skips Update-Hover before card.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import ROOT

WATCH = ROOT / "third_party" / "bob-tray" / "tools" / "Watch-BobTray.ps1"
DOCS = ROOT / "docs" / "bob-9171-menuarm-timestamp.md"
DOCS_9163 = ROOT / "docs" / "bob-9163-menu-sticky-clear.md"
WIN = pytest.mark.skipif(sys.platform != "win32", reason="tray PowerShell")


def test_fr9171_opening_uses_timestamp_not_disable():
    t = WATCH.read_text(encoding="utf-8")
    assert "FR #9171" in t
    opening = t[t.index("$menu.Add_Opening") : t.index("$menu.Add_Opened")]
    assert "bobTrayMenuArmedAt" in opening or "MenuArmedAt" in opening
    assert "Enabled = $false" not in opening
    assert "Set-BobTrayMenuItemsEnabled -Menu $menu -Enabled $false" not in opening
    assert "350" in opening or "MenuArmMs" in t
    assert "MenuItemsArmed" in opening


def test_fr9171_exit_ignores_clicks_inside_arm_window():
    t = WATCH.read_text(encoding="utf-8")
    exit_click = t[t.index("$miExit.Add_Click") : t.index("$miExit.Add_Click") + 900]
    assert "Test-BobTrayMenuArmReady" in exit_click or "bobTrayMenuArmedAt" in exit_click
    assert "ExitArmIgnored" in exit_click or "arm" in exit_click.lower()


def test_fr9171_status_dismisses_stuck_menu():
    t = WATCH.read_text(encoding="utf-8")
    status = t[t.index("function Invoke-BobTrayStatus") : t.index("function Invoke-BobTrayStatus") + 1600]
    assert "StatusMenuDismiss" in status
    assert "Close()" in status or ".Close(" in status
    # Park path must not call bare Update-Hover before Show-BobTrayCard
    assert "Show-BobTrayCard" in status
    park = status
    # After park detect, no Update-Hover line before Show-BobTrayCard
    if "Test-BobTrayClickFixParkPresent" in park:
        after_park = park[park.index("Test-BobTrayClickFixParkPresent") :]
        show_at = after_park.index("Show-BobTrayCard")
        before_show = after_park[:show_at]
        assert "Update-Hover" not in before_show


def test_fr9171_show_card_clears_sticky_when_hidden():
    t = WATCH.read_text(encoding="utf-8")
    show = t[t.index("function Show-BobTrayCard") : t.index("function Show-BobTrayCard") + 900]
    assert "Clear-BobTrayMenuOpenIfHidden" in show


def test_fr9171_evidence_and_9163_doc():
    assert DOCS.is_file()
    text = DOCS.read_text(encoding="utf-8")
    assert "FR #9171" in text
    assert "9170" in text
    assert "timestamp" in text.lower() or "ArmedAt" in text
    assert "Enabled" in text
    d9163 = DOCS_9163.read_text(encoding="utf-8")
    assert "9171" in d9163


@WIN
def test_fr9171_arm_ready_helper(tmp_path: Path):
    t = WATCH.read_text(encoding="utf-8")
    assert "function Test-BobTrayMenuArmReady" in t
    start = t.index("function Test-BobTrayMenuArmReady")
    nxt = t.find("\nfunction ", start + 1)
    excerpt = t[start:nxt]
    # Also need MenuArmMs constant if referenced
    arm_ms = ""
    if "BobTrayMenuArmMs" in t:
        # pull a small assignment snippet
        i = t.index("BobTrayMenuArmMs")
        arm_ms = "$script:BobTrayMenuArmMs = 350\n"
    script = tmp_path / "a.ps1"
    script.write_text(
        "function Write-TrayLog { param($m) }\n"
        + arm_ms
        + excerpt
        + "\n"
        + "\n".join(
            [
                "$script:bobTrayMenuArmedAt = $null",
                "$r0 = Test-BobTrayMenuArmReady",
                'Write-Output ("null={0}" -f $r0)',
                "$script:bobTrayMenuArmedAt = [datetime]::UtcNow.AddMilliseconds(-500)",
                "$r1 = Test-BobTrayMenuArmReady",
                'Write-Output ("old={0}" -f $r1)',
                "$script:bobTrayMenuArmedAt = [datetime]::UtcNow",
                "$r2 = Test-BobTrayMenuArmReady",
                'Write-Output ("fresh={0}" -f $r2)',
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
    assert "null=True" in out
    assert "old=True" in out
    assert "fresh=False" in out
