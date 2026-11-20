"""FR #8577: Start-JeevesMonitor tolerates drive-root InstallRoot (J:\\)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import REPO

SCRIPTS = REPO / "jeeves" / "scripts"
MONITOR = SCRIPTS / "Start-JeevesMonitor.ps1"
MAINT = SCRIPTS / "Start-JeevesMaintenance.ps1"
COMMON = REPO / "common" / "scripts" / "Bobiverse-Common.ps1"

WIN = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("powershell"),
    reason="needs Windows PowerShell",
)


def test_monitor_script_has_drive_root_bob_fallback():
    text = MONITOR.read_text(encoding="utf-8-sig")
    assert "IsNullOrWhiteSpace($ai)" in text
    assert "Pass -BobInstallRoot" in text
    assert "Normalize-JeevesRoot" in text
    assert "Resolve-BobInstallRootFromJeeves" in text
    assert r"ai\bob" in text
    assert "Split-Path -Parent $JeevesRoot" in text or "Split-Path -Parent $InstallRoot" in text


def test_maintenance_script_has_drive_root_bob_fallback():
    text = MAINT.read_text(encoding="utf-8-sig")
    assert "IsNullOrWhiteSpace($ai)" in text
    assert "Pass -BobInstallRoot" in text


def test_shortcut_spec_passes_bob_install_root():
    text = COMMON.read_text(encoding="utf-8-sig")
    assert "Start-JeevesMonitor.ps1" in text
    # FR #8577: shortcut argv includes -BobInstallRoot when bob exe is found
    assert "-BobInstallRoot" in text
    idx = text.index('$mon = Join-Path $scr \'Start-JeevesMonitor.ps1\'')
    window = text[idx : idx + 1200]
    assert "-BobInstallRoot" in window
    assert "FR #8577" in window


@WIN
def test_drive_root_installroot_resolves_bob_without_empty_path(tmp_path: Path):
    """subst a drive letter so InstallRoot parent is empty; script must not throw Join-Path ''."""
    jeeves = tmp_path / "jeeves_root"
    jeeves.mkdir()
    (jeeves / "AGENTS.md").write_text("# test\n", encoding="utf-8")
    # Prefer a free letter near the end of the alphabet
    letter = None
    for cand in "ZYXWVUTSRQPONMLKJIHGFED":
        if not Path(f"{cand}:\\").exists():
            letter = cand
            break
    if letter is None:
        pytest.skip("no free drive letter for subst")
    root = f"{letter}:\\"
    # Point subst at the temp jeeves folder (InstallRoot = drive root)
    subst = subprocess.run(
        ["subst", f"{letter}:", str(jeeves)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if subst.returncode != 0:
        pytest.skip(f"subst failed: {subst.stderr or subst.stdout}")
    try:
        bob = Path(os.environ.get("SystemDrive", "C:") + r"\ai\bob")
        exe = bob / "worker" / "bob-worker.exe"
        if not exe.is_file():
            # Create a minimal fake exe under C:\ai\bob if missing so DryRun path can resolve;
            # prefer real install when present.
            pytest.skip("C:\\ai\\bob\\worker\\bob-worker.exe missing for fallback probe")
        # Probe resolution only: stop before Start-Process by using a wrapper that
        # dotsources the resolve path. Invoke script with -DryRun; bob-worker --dry-run
        # may exit nonzero without fuel — we only assert no empty-Path Join-Path error.
        ps = f"""
$ErrorActionPreference = 'Stop'
try {{
  & '{MONITOR}' -InstallRoot '{root}' -DryRun 2>&1 | Out-String | Write-Output
  exit 0
}} catch {{
  $m = $_.Exception.Message
  if ($m -match 'empty string' -or $m -match \"Cannot bind argument to parameter 'Path'\") {{
    Write-Output ('FAIL_EMPTY_PATH: ' + $m)
    exit 11
  }}
  # Other errors (missing fuel, dry-run worker) are OK for this pin
  Write-Output ('OTHER: ' + $m)
  exit 0
}}
"""
        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        out = (r.stdout or "") + (r.stderr or "")
        assert r.returncode != 11, out
        assert "FAIL_EMPTY_PATH" not in out, out
        assert "empty string" not in out.lower() or "OTHER:" in out
    finally:
        subprocess.run(
            ["subst", f"{letter}:", "/d"],
            capture_output=True,
            text=True,
            timeout=30,
        )


@WIN
def test_explicit_bob_install_root_on_drive_root(tmp_path: Path):
    jeeves = tmp_path / "jroot"
    bob = tmp_path / "bob"
    (jeeves).mkdir()
    (bob / "worker").mkdir(parents=True)
    (jeeves / "AGENTS.md").write_text("# test\n", encoding="utf-8")
    fake = bob / "worker" / "bob-worker.exe"
    # Tiny PE-less placeholder is enough for Test-Path; DryRun will fail later — we only
    # assert resolve + copy path does not hit empty Join-Path. Use cmd copy of real exe if present.
    real = Path(r"C:\ai\bob\worker\bob-worker.exe")
    if real.is_file():
        shutil.copy2(real, fake)
    else:
        fake.write_bytes(b"MZFAKE")
    letter = None
    for cand in "ZYXWVUTSRQPONMLKJIHGFED":
        if not Path(f"{cand}:\\").exists():
            letter = cand
            break
    if letter is None:
        pytest.skip("no free drive letter for subst")
    root = f"{letter}:\\"
    subst = subprocess.run(
        ["subst", f"{letter}:", str(jeeves)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if subst.returncode != 0:
        pytest.skip(f"subst failed: {subst.stderr or subst.stdout}")
    try:
        # Resolution probe without launching: parse script functions via a tiny harness
        harness = f"""
$ErrorActionPreference = 'Stop'
$InstallRoot = '{root}'
$BobInstallRoot = '{bob}'
# Mimic script normalize + exe check
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot.TrimEnd() + $(if ($InstallRoot -match '^[A-Za-z]:$') {{ '\\' }} else {{ '' }}))
if ($InstallRoot -match '^[A-Za-z]:$') {{ $InstallRoot = $InstallRoot + '\\' }}
try {{ $InstallRoot = [IO.Path]::GetFullPath($InstallRoot) }} catch {{ $InstallRoot = ($InstallRoot.Substring(0,2) + '\\') }}
$BobInstallRoot = [IO.Path]::GetFullPath('{bob}')
$exe = Join-Path $BobInstallRoot 'worker\\bob-worker.exe'
if (-not (Test-Path -LiteralPath $exe)) {{ throw 'exe missing' }}
if (-not (Test-Path -LiteralPath (Join-Path $InstallRoot 'AGENTS.md'))) {{ throw 'agents missing' }}
Write-Output ('OK InstallRoot=' + $InstallRoot + ' Bob=' + $BobInstallRoot)
# Also run real script dry-run with explicit -BobInstallRoot
try {{
  & '{MONITOR}' -InstallRoot '{root}' -BobInstallRoot '{bob}' -DryRun *>$null
}} catch {{
  if ($_.Exception.Message -match 'empty string') {{ throw }}
}}
Write-Output 'OK_SCRIPT'
"""
        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                harness,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        out = (r.stdout or "") + (r.stderr or "")
        assert r.returncode == 0, out
        assert "OK_SCRIPT" in out, out
        assert "empty string" not in out.lower()
    finally:
        subprocess.run(
            ["subst", f"{letter}:", "/d"],
            capture_output=True,
            text=True,
            timeout=30,
        )
