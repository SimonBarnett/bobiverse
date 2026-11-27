# -*- coding: utf-8 -*-
"""FR #9689: Pack/Sync stage vendor\\jeeves\\JeevesAgent.exe (jeeves-mcp Phase 0)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from repo_layout import ROOT

PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
SYNC = ROOT / "common" / "scripts" / "Sync-BobiverseFromRepo.ps1"
COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"


def test_fr9689_pack_pins_vendor_jeeves_paths():
    pack = PACK.read_text(encoding="utf-8-sig")
    assert "9689" in pack
    assert r"vendor\jeeves\JeevesAgent.exe" in pack or "vendor\\jeeves\\JeevesAgent.exe" in pack
    assert "Copy-BobTrayVendorExes" in pack
    assert "jeeves-mcp" in pack
    assert "BOB_JEEVES_AGENT_RELEASE_TAG" in pack
    assert "JeevesAgent.exe" in pack
    # FIX #9742: GitHub Actions may stub when the jeeves-mcp release does not exist yet.
    assert "GITHUB_ACTIONS" in pack
    assert "ci-missing-release" in pack


def test_fr9689_sync_mirrors_jeeves_into_vendor():
    sync = SYNC.read_text(encoding="utf-8-sig")
    common = COMMON.read_text(encoding="utf-8-sig")
    assert "9689" in sync or "9689" in common
    assert "Copy-BobTrayVendorExes" in common
    assert "Copy-BobTrayVendorExes" in sync
    assert "JeevesAgent.exe" in common


def test_fr9689_copy_helper_stages_vendor_jeeves_exe(tmp_path: Path):
    """Offline: Copy-BobTrayVendorExes mirrors jeeves into vendor JeevesAgent only."""
    root = tmp_path / "install"
    # -Require also needs plan + priority sources (FR #9468); stub them for isolation.
    for name, stub in (
        ("plan", b"MZ-plan-stub"),
        ("priority", b"MZ-priority-stub"),
        ("jeeves", b"MZ-jeeves-stub"),
    ):
        d = root / name
        d.mkdir(parents=True)
        exe = "PlanAgent.exe" if name == "plan" else (
            "PriorityAgent.exe" if name == "priority" else "JeevesAgent.exe"
        )
        (d / exe).write_bytes(stub)
    (root / "jeeves" / "JeevesAgent.MANIFEST.json").write_text(
        '{"tag":"launcher-v1.0.0","repo":"SimonBarnett/jeeves-mcp"}\n',
        encoding="utf-8",
    )

    ps = f"""
$ErrorActionPreference = 'Stop'
. '{COMMON}'
$r = Copy-BobTrayVendorExes -Root '{root}' -Require
if (-not $r.ok) {{ throw 'helper returned not ok' }}
$ja = Join-Path '{root}' 'vendor\\jeeves\\JeevesAgent.exe'
if (-not (Test-Path -LiteralPath $ja -PathType Leaf)) {{ throw 'missing JeevesAgent.exe' }}
if (-not (Test-Path -LiteralPath (Join-Path '{root}' 'vendor\\jeeves\\JeevesAgent.exe.sha256') -PathType Leaf)) {{
  throw 'missing JeevesAgent.exe.sha256'
}}
Write-Output 'STAGE_OK'
"""
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    assert "STAGE_OK" in (r.stdout or "")
    assert (root / "vendor" / "jeeves" / "JeevesAgent.exe").is_file()


def test_fr9689_copy_helper_require_throws_when_sources_missing(tmp_path: Path):
    root = tmp_path / "empty"
    root.mkdir()
    ps = f"""
$ErrorActionPreference = 'Stop'
. '{COMMON}'
try {{
  Copy-BobTrayVendorExes -Root '{root}' -Require | Out-Null
  throw 'expected throw'
}} catch {{
  if ($_.Exception.Message -notmatch '9689|9468') {{ throw $_ }}
  Write-Output 'THROW_OK'
}}
"""
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    assert "THROW_OK" in (r.stdout or "")
