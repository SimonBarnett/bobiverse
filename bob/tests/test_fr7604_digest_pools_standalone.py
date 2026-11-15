"""FR #7604: Update-BobTrayDigestPools standalone URL + always write pools or fail."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
HELPER = ROOT / "tray" / "tools" / "Update-BobTrayDigestPools.ps1"
DIALOGS = ROOT / "tray" / "tools" / "BobTrayDialogs.ps1"
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"
PS = os.environ.get("BOB_TEST_POWERSHELL") or shutil.which("powershell") or shutil.which("pwsh")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")
CANON = "https://bob.ntsa.uk/bob/v1/report"


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def _ps(script: str, timeout: int = 90) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_fr7604_hover_defines_digest_url_standalone():
    h = _txt(HOVER)
    assert "function Get-BobTrayDigestReportUrl" in h
    assert "FR #7604" in h
    start = h.index("function Get-BobTrayDigestReportUrl")
    block = h[start : start + 400]
    assert CANON in block
    assert ".Trim()" in block
    assert "Write-BobTrayDigestFetchFailFile" in h


def test_fr7604_helper_script_pins_standalone_contract():
    t = _txt(HELPER)
    assert "FR #7604" in t
    assert "Get-BobTrayDigestReportUrl not loaded" in t
    assert "tray-digest-fetch-fail.json" in t
    assert "neither pools nor fail" in t
    # Must not require Watch-BobTray.
    assert "Watch-BobTray" not in t


def test_fr7604_no_machine_names_in_helper():
    blob = (_txt(HELPER) + _txt(HOVER)[ _txt(HOVER).index("function Get-BobTrayDigestReportUrl") :
                                         _txt(HOVER).index("function Update-BobTrayDigestPools") + 800]).lower()
    for banned in ("red" + "queen", "flam" + "ingo", "march" + "hare"):
        assert banned not in blob


@needs_ps
def test_fr7604_standalone_file_writes_pools_or_fail(tmp_path: Path):
    """Clean session: -File helper only (no Watch-BobTray); fixture digest -> pools file."""
    root = tmp_path / "install"
    (root / "run").mkdir(parents=True)
    # Flat layout the helper expects.
    pub = root / "src" / "Public"
    pub.mkdir(parents=True)
    priv = root / "src" / "Private"
    priv.mkdir(parents=True)
    tools = root / "tools"
    tools.mkdir(parents=True)
    shutil.copy2(HOVER, pub / "Get-BobTrayHover.ps1")
    shutil.copy2(DIALOGS, tools / "BobTrayDialogs.ps1")
    shutil.copy2(HELPER, tools / "Update-BobTrayDigestPools.ps1")
    dig = tmp_path / "digest.json"
    dig.write_text(
        json.dumps(
            {
                "machines": {
                    "box": {
                        "xai_weekly": {
                            "remaining_pct": 42,
                            "fresh": True,
                            "fetched_at": "2026-11-15T18:00:00Z",
                        }
                    }
                },
                "copilot": {"state": "ok", "used": 1, "fresh": True},
            }
        ),
        encoding="utf-8",
    )
    r = subprocess.run(
        [
            PS,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(tools / "Update-BobTrayDigestPools.ps1"),
            "-Root",
            str(root),
            "-DigestPath",
            str(dig),
        ],
        capture_output=True,
        text=True,
        timeout=90,
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out
    pools = root / "run" / "tray-digest-pools.json"
    fail = root / "run" / "tray-digest-fetch-fail.json"
    assert pools.is_file() or fail.is_file(), out
    if pools.is_file():
        doc = json.loads(pools.read_text(encoding="utf-8"))
        assert "ts" in doc
        assert doc.get("digest_ok") is True


@needs_ps
def test_fr7604_empty_url_writes_fail_and_reports(tmp_path: Path, monkeypatch):
    root = tmp_path / "install"
    root.mkdir()
    reports: list[str] = []
    script = f"""
$ErrorActionPreference = 'Stop'
. '{HOVER}'
. '{DIALOGS}'
function Get-BobTrayDigestReportUrl {{ return '' }}
$script:reported = @()
function Report-BobDeterministicException {{
  param($Site, $Exception, $ScriptPath, $Repo, $DedupeHours, $Force)
  $script:reported += [string]$Site
  return @{{ ok = $true; skipped = $true }}
}}
$p = Update-BobTrayDigestPools -Root '{root}' -Url ''
$fail = Join-Path '{root}' 'run\\tray-digest-fetch-fail.json'
$j = Get-Content -LiteralPath $fail -Raw -Encoding UTF8 | ConvertFrom-Json
[ordered]@{{
  has_fail = [bool](Test-Path -LiteralPath $fail)
  reason = [string]$j.reason
  note = [string]$j.note
  err = [string]$j.error
  ts = [int64]$j.ts
  reported = @($script:reported)
  pools = [bool](Test-Path -LiteralPath (Join-Path '{root}' 'run\\tray-digest-pools.json'))
}} | ConvertTo-Json -Compress
"""
    r = _ps(script)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    data = json.loads((r.stdout or "").strip().splitlines()[-1])
    assert data["has_fail"] is True
    assert data["ts"] > 0
    blob = (data.get("reason") or "") + " " + (data.get("note") or "") + " " + (data.get("err") or "")
    assert re.search(r"empty", blob, re.I), data
    assert "Update-BobTrayDigestPools" in (data.get("reported") or [])
    assert data["pools"] is True  # still writes pools with digest_ok=false


@needs_ps
def test_fr7604_exception_writes_fail_and_reports(tmp_path: Path):
    root = tmp_path / "install"
    root.mkdir()
    missing = tmp_path / "no-such-digest.json"
    script = f"""
$ErrorActionPreference = 'Stop'
. '{HOVER}'
. '{DIALOGS}'
$script:reported = @()
function Report-BobDeterministicException {{
  param($Site, $Exception, $ScriptPath, $Repo, $DedupeHours, $Force)
  $script:reported += [string]$Site
  return @{{ ok = $true }}
}}
$null = Update-BobTrayDigestPools -Root '{root}' -DigestPath '{missing}'
$fail = Join-Path '{root}' 'run\\tray-digest-fetch-fail.json'
$j = Get-Content -LiteralPath $fail -Raw -Encoding UTF8 | ConvertFrom-Json
[ordered]@{{
  has_fail = [bool](Test-Path -LiteralPath $fail)
  reason = [string]$j.reason
  ts = [int64]$j.ts
  reported = @($script:reported)
}} | ConvertTo-Json -Compress
"""
    r = _ps(script)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    data = json.loads((r.stdout or "").strip().splitlines()[-1])
    assert data["has_fail"] is True
    assert data["ts"] > 0
    assert re.search(r"unreachable|missing|digest", data.get("reason") or "", re.I), data
    assert "Update-BobTrayDigestPools" in (data.get("reported") or [])
