"""FR #9526: Get-BobTrayPriorProcessHits Get-Process fallback must parse on WinPS 5.1.

A try/catch expression as a hashtable value is a ParserError on Windows PowerShell 5.1
and blocks Start-BobFleetTray -ForceNew after the tip lands (Install-BobTrayHotpatch dotsource).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIFE = ROOT / "bob" / "tray" / "tools" / "BobTrayLifecycle.ps1"


def test_lifecycle_ps1_exists():
    assert LIFE.is_file(), LIFE


def test_no_try_as_hashtable_value_for_executable_path():
    text = LIFE.read_text(encoding="utf-8")
    assert "function Get-BobTrayPriorProcessHits" in text
    assert "ExecutablePath = try {" not in text
    assert "$exePath" in text
    gp = text.split("Get-Process -Name 'bob-tray'", 1)[1]
    assert gp.index("try {") < gp.index("$hits.Add([pscustomobject]@{")


def test_lifecycle_parses_in_powershell():
    path = str(LIFE).replace("'", "''")
    d = chr(36)
    script = (
        f"{d}e = {d}null; "
        f"[void][System.Management.Automation.Language.Parser]::ParseFile('{path}', [ref]{d}null, [ref]{d}e); "
        f"if ({d}e -and {d}e.Count -gt 0) {{ {d}e | ForEach-Object {{ {d}_.ToString() }}; exit 1 }}; "
        "Write-Output 'parse_ok'"
    )
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, (r.stdout + r.stderr)[:800]
    assert "parse_ok" in r.stdout
