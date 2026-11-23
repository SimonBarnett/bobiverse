"""FR #8733 / BOB-28: Workers > Open Code paid exhausted dialog + quit.

S1: Fixture free=0 paid=0 → dialog + quit (no start). Fail-when: starts with no fuel.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import REPO

WIN = sys.platform == "win32"
CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
PS = shutil.which("powershell.exe") or shutil.which("powershell") or shutil.which("pwsh")

TRAY_CS = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
GATE_CS = REPO / "bob" / "tray" / "dialogs" / "OpenCodePaidExhaustedGate.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
BUILD = REPO / "bob" / "scripts" / "Build-BobDialogs.ps1"
PACK = REPO / "bob" / "docs" / "feature-request-workers-opencode-paid-exhausted-2026-11-21.md"
DOC = REPO / "bob" / "docs" / "bob-28-opencode-paid-exhausted.md"


def test_fr8733_sources_pin_paid_exhausted_gate():
    cs = TRAY_CS.read_text(encoding="utf-8-sig")
    gate = GATE_CS.read_text(encoding="utf-8-sig")
    ps = WATCH.read_text(encoding="utf-8-sig")
    assert "OpenCodePaidExhaustedGate" in cs
    assert "paid-exhausted" in cs
    assert "--check-opencode-paid-exhausted" in cs
    assert "IsExhaustedDocument" in gate
    assert '"free"' in gate and ("\"go\"" in gate or '"go"' in gate)
    assert "Test-BobTrayOpenCodePaidExhausted" in ps
    assert "Show-BobTrayOpenCodePaidExhaustedDialog" in ps
    assert "paid exhausted dialog + quit" in ps
    assert "BOB-28" in PACK.read_text(encoding="utf-8")
    assert "free and paid" in DOC.read_text(encoding="utf-8")


def test_fr8733_ps_gate_free0_paid0(tmp_path: Path):
    if not PS:
        pytest.skip("powershell missing")
    fuel = tmp_path / "opencode-fuel.json"
    fuel.write_text(json.dumps({"free": 0, "go": 0}), encoding="utf-8")
    # Non-exhausted control
    fuel_ok = tmp_path / "ok.json"
    fuel_ok.write_text(json.dumps({"free": 0, "go": 40}), encoding="utf-8")
    # Unknown go must not gate
    fuel_unk = tmp_path / "unk.json"
    fuel_unk.write_text(json.dumps({"free": 0, "go": None}), encoding="utf-8")
    inline = r"""
function Test-BobTrayOpenCodePaidExhausted {
  param([string]$InstallRoot = '', [string]$FuelPath = '')
  $path = ([string]$FuelPath).Trim()
  if (-not $path) { return $false }
  if (-not (Test-Path -LiteralPath $path)) { return $false }
  try { $doc = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json } catch { return $false }
  if (-not $doc) { return $false }
  $free = $null; $paid = $null
  try { if ($null -ne $doc.free -and [string]$doc.free -ne '') { $free = [int]$doc.free } } catch { }
  try { if ($null -ne $doc.go -and [string]$doc.go -ne '') { $paid = [int]$doc.go } } catch { }
  if ($null -eq $free -or $null -eq $paid) { return $false }
  return ($free -le 0 -and $paid -le 0)
}
"""
    cmd = (
        inline
        + f"\nif (Test-BobTrayOpenCodePaidExhausted -FuelPath '{fuel}') {{ 'ex=1' }} else {{ 'ex=0' }}"
        + f"\nif (Test-BobTrayOpenCodePaidExhausted -FuelPath '{fuel_ok}') {{ 'ok=1' }} else {{ 'ok=0' }}"
        + f"\nif (Test-BobTrayOpenCodePaidExhausted -FuelPath '{fuel_unk}') {{ 'unk=1' }} else {{ 'unk=0' }}"
    )
    r = subprocess.run(
        [PS, "-NoProfile", "-Command", cmd],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ex=1" in r.stdout
    assert "ok=0" in r.stdout
    assert "unk=0" in r.stdout


@pytest.mark.skipif(not (WIN and CSC.is_file() and PS), reason="needs Windows csc and powershell")
def test_fr8733_tray_headless_check_paid_exhausted(tmp_path: Path):
    out_dir = tmp_path / "dlg"
    r = subprocess.run(
        [
            PS,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(BUILD),
            "-RepoRoot",
            str(REPO),
            "-OutDir",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    tray = out_dir / "bob-tray.exe"
    assert tray.is_file()

    root = tmp_path / "root"
    run = root / "run"
    run.mkdir(parents=True)
    (run / "opencode-fuel.json").write_text(
        json.dumps({"free": 0, "go": 0}), encoding="utf-8"
    )
    out = tmp_path / "gate.json"
    p = subprocess.run(
        [
            str(tray),
            "--root",
            str(root),
            "--check-opencode-paid-exhausted",
            str(out),
            "--no-engine",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert p.returncode == 2, p.stdout + p.stderr + (
        out.read_text(encoding="utf-8") if out.is_file() else ""
    )
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc.get("exhausted") is True
    assert doc.get("gate") == "opencode-paid-exhausted"

    (run / "opencode-fuel.json").write_text(
        json.dumps({"free": 0, "go": 25}), encoding="utf-8"
    )
    out2 = tmp_path / "gate2.json"
    p2 = subprocess.run(
        [
            str(tray),
            "--root",
            str(root),
            "--check-opencode-paid-exhausted",
            str(out2),
            "--no-engine",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert p2.returncode == 0
    assert json.loads(out2.read_text(encoding="utf-8")).get("exhausted") is False

    # Missing fuel file → no gate
    (run / "opencode-fuel.json").unlink()
    out3 = tmp_path / "gate3.json"
    p3 = subprocess.run(
        [
            str(tray),
            "--root",
            str(root),
            "--check-opencode-paid-exhausted",
            str(out3),
            "--no-engine",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert p3.returncode == 0
    assert json.loads(out3.read_text(encoding="utf-8")).get("exhausted") is False
