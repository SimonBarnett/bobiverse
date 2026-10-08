"""FR #3391: Install-Airc.ps1 must parse under WinPS 5.1 (ASCII, BOM-less).

BOM-less + em-dash inside a double-quoted string broke MSI RunInstall (1603).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from repo_layout import ROOT

INSTALL = ROOT / "airc" / "scripts" / "Install-Airc.ps1"

# Scripts the airc / bob / jeeves MSI trees stage (or ship beside RunInstall).
_STAGED_GLOBS = (
    "airc/scripts/*.ps1",
    "common/scripts/*.ps1",
    "bob/scripts/*.ps1",
    "jeeves/scripts/*.ps1",
)


def _staged_ps1() -> list[Path]:
    out: list[Path] = []
    for pattern in _STAGED_GLOBS:
        out.extend(sorted(ROOT.glob(pattern)))
    # Dedupe while preserving order
    seen: set[Path] = set()
    uniq: list[Path] = []
    for p in out:
        rp = p.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        uniq.append(p)
    return uniq


def test_fr3391_install_airc_ascii_no_bom_hostile_appparameters_line():
    raw = INSTALL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "keep BOM-less (test_fr3292 / _no_bom)"
    text = raw.decode("utf-8")
    assert not any(ord(ch) > 127 for ch in text), (
        "Unicode punctuation breaks quiet MSI CA on WinPS 5.1 when BOM-less"
    )
    # Hostile pin: the former em-dash line that closed the double-quoted string early.
    assert 'Write-Host "INFO FR #1552: no AppParameters - using $snapPath"' in text


@pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="powershell.exe missing")
def test_fr3391_install_airc_parses_under_powershell():
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
    env = dict(os.environ)
    env["AIRC_INSTALL_SCRIPT"] = str(INSTALL)
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


@pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="powershell.exe missing")
def test_fr3391_staged_ps1_parse_and_bomless_ascii():
    """Every staged *.ps1: ParseFile 0 errors; BOM-less files must be pure ASCII."""
    files = _staged_ps1()
    assert files, "expected staged *.ps1 under airc|common|bob|jeeves/scripts"
    assert INSTALL.resolve() in {p.resolve() for p in files}

    bad_non_ascii: list[str] = []
    for path in files:
        raw = path.read_bytes()
        if not raw.startswith(b"\xef\xbb\xbf"):
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                bad_non_ascii.append(f"{path.relative_to(ROOT)}: decode {exc}")
                continue
            if any(ord(ch) > 127 for ch in text):
                bad_non_ascii.append(str(path.relative_to(ROOT)))

    assert not bad_non_ascii, (
        "BOM-less *.ps1 with non-ASCII (WinPS 5.1 ANSI mis-parse risk):\n"
        + "\n".join(bad_non_ascii[:40])
    )

    # Batch ParseFile via one powershell process for speed.
    # Pass paths as newline-separated env to avoid command-line length limits.
    listing = "\n".join(str(p) for p in files)
    env = dict(os.environ)
    env["BOB_PARSE_PS1_LIST"] = listing
    ps = r"""
$ErrorActionPreference = 'Stop'
$paths = ($env:BOB_PARSE_PS1_LIST -split "`n") | Where-Object { $_ -and $_.Trim() }
$failed = @()
foreach ($path in $paths) {
  $errs = $null
  $null = [System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$null, [ref]$errs)
  if ($errs -and $errs.Count -gt 0) {
    $rel = $path
    $failed += ("{0}: {1}" -f $rel, ($errs | ForEach-Object { $_.ToString() } | Select-Object -First 3) -join '; ')
  }
}
if ($failed.Count -gt 0) {
  $failed | ForEach-Object { Write-Output $_ }
  exit 2
}
Write-Output ("PARSE_OK count={0}" -f $paths.Count)
exit 0
"""
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, out
    assert "PARSE_OK" in out, out
