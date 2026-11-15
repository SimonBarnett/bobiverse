"""FR #7693: a null TitleColor must not throw during the tray hover paint."""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "bob" / "tray" / "tools" / "BobTrayDrawingColor.ps1"
WATCH = ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"


def _ps(body: str) -> str:
    script = (
        "Add-Type -AssemblyName System.Drawing\n"
        f". '{HELPER}'\n"
        + body
    )
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return proc.stdout


def test_fr7693_null_or_missing_colour_is_default():
    out = _ps(
        "$missing = Resolve-BobTrayDrawingColor\n"
        "$nullIn = Resolve-BobTrayDrawingColor -Color $null\n"
        "$blank = Resolve-BobTrayDrawingColor -Color ''\n"
        "if ($null -ne $missing -or $null -ne $nullIn -or $null -ne $blank) { exit 2 }\n"
        "Write-Output 'default'\n"
    )
    assert "default" in out


def test_fr7693_valid_colour_unchanged():
    out = _ps(
        "$c = Resolve-BobTrayDrawingColor -Color ([System.Drawing.Color]::FromArgb(255, 10, 20, 30))\n"
        "Write-Output ('{0},{1},{2},{3}' -f $c.A, $c.R, $c.G, $c.B)\n"
    )
    assert "255,10,20,30" in out.replace(" ", "")


def test_fr7693_hover_catch_still_reports():
    text = WATCH.read_text(encoding="utf-8-sig")
    hover = text.split("function Update-Hover", 1)[1].split("\nfunction ", 1)[0]
    assert "hover error:" in hover
    assert "Invoke-BobMustReportFailure" in hover
    assert "tray.hover" in hover
    # Typed Color parameters throw on $null before the body. They must be gone.
    header = text.split("function Add-BobTraySectionHeader", 1)[1].split("function Set-BobTrayHelpTip", 1)[0]
    assert "[System.Drawing.Color]$TitleColor" not in header
    assert "Resolve-BobTrayDrawingColor -Color $TitleColor" in header
    row = text.split("function Add-BobTrayFuelFamilyRow", 1)[1].split("function Get-BobTrayLogoImage", 1)[0]
    assert "[System.Drawing.Color]$TitleColor" not in row
