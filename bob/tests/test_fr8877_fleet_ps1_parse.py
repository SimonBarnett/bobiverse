"""FR #8877: Invoke-BobFleet.ps1 build-loop helpers must parse (dollars kept)."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from repo_layout import ROOT

FLEET = ROOT / "tray" / "src" / "Private" / "Invoke-BobFleet.ps1"


def test_fr8877_helpers_keep_dollar_names():
    text = FLEET.read_text(encoding="utf-8-sig")
    assert "param([string]$Body)" in text
    assert "param(\n        [Parameter(Mandatory)][string]$Issue," in text
    assert "[string]$JobId" in text
    assert "[string]$Machine" in text
    assert "return $false" in text
    assert "return $true" in text
    assert "param([string])" not in text
    assert "return False" not in text


def test_fr8877_invoke_bobfleet_parses():
    ps = shutil.which("powershell") or shutil.which("pwsh")
    assert ps
    script = (
        "$e=$null; $t=$null; "
        "[void][System.Management.Automation.Language.Parser]::ParseFile("
        f"'{FLEET}', [ref]$t, [ref]$e); "
        "if ($e -and $e.Count) { $e | ForEach-Object { $_.ToString() }; exit 1 }"
    )
    r = subprocess.run(
        [ps, "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert r.returncode == 0, r.stdout + "\n" + r.stderr
