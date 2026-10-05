"""FR #2499: Install-AircConsole must parse under WinPS 5.1; no $Home param bind."""
from __future__ import annotations

import subprocess
from pathlib import Path

from repo_layout import ROOT

SCRIPT = ROOT / "airc" / "scripts" / "Install-AircConsole.ps1"


def test_fr2499_install_airc_console_is_ascii_punctuation():
    text = SCRIPT.read_text(encoding="utf-8")
    assert not any(ord(ch) > 127 for ch in text), "Unicode punctuation breaks quiet MSI CA on WinPS 5.1"
    assert "[string]$Home," not in text
    assert "$HomePath" in text
    assert "[Alias('Home')]" in text or '[Alias("Home")]' in text


def test_fr2499_install_airc_console_parses_under_powershell():
    raw = SCRIPT.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    ps = r"""
$ErrorActionPreference = 'Stop'
$path = $env:AIRC_INSTALL_SCRIPT
$errs = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$null, [ref]$errs)
if ($errs -and $errs.Count -gt 0) {
  $errs | ForEach-Object { Write-Output $_.ToString() }
  exit 2
}
Write-Output 'PARSE_OK'
exit 0
"""
    env = dict(**{k: v for k, v in __import__("os").environ.items()})
    env["AIRC_INSTALL_SCRIPT"] = str(SCRIPT)
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, out
    assert "PARSE_OK" in out, out
