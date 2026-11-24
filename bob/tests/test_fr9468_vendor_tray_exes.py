# -*- coding: utf-8 -*-
"""FR #9468 / #9598: Pack/Sync stage vendor\\plan\\PlanAgent.exe + vendor\\priority\\PriorityAgent.exe (no bob-plan)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from repo_layout import ROOT

PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
SYNC = ROOT / "common" / "scripts" / "Sync-BobiverseFromRepo.ps1"
COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
EVIDENCE49 = ROOT / "bob" / "docs" / "bob-49-bob-ear-msi-include-plan-evidence.md"
EVIDENCE55 = ROOT / "bob" / "docs" / "bob-55-bob-ear-msi-include-priority-evidence.md"
TRAY = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"


def test_fr9468_pack_pins_vendor_tray_paths():
    pack = PACK.read_text(encoding="utf-8-sig")
    assert "9468" in pack
    assert "9598" in pack
    assert r"vendor\plan\PlanAgent.exe" in pack or "vendor\\plan\\PlanAgent.exe" in pack
    assert "bob-plan.exe" in pack  # fail-closed reject of legacy twin
    assert r"vendor\priority\PriorityAgent.exe" in pack or "vendor\\priority\\PriorityAgent.exe" in pack
    assert "Copy-BobTrayVendorExes" in pack
    assert "skills-visionary" in pack
    assert "priority-mcp" in pack
    assert "BOB_PLAN_AGENT_RELEASE_TAG" in pack
    assert "BOB_PRIORITY_AGENT_RELEASE_TAG" in pack


def test_fr9468_sync_mirrors_plan_priority_into_vendor():
    sync = SYNC.read_text(encoding="utf-8-sig")
    common = COMMON.read_text(encoding="utf-8-sig")
    assert "9468" in sync or "9468" in common
    assert "Copy-BobTrayVendorExes" in common
    assert "Copy-BobTrayVendorExes" in sync
    assert "PlanAgent.exe" in common
    assert "9598" in common
    # Must not Copy-Item PlanAgent into bob-plan.exe (stale Remove-Item of leftover twins is OK).
    assert "Destination (Join-Path $vendorPlan 'bob-plan.exe')" not in common
    assert "Copy-Item -LiteralPath $planSrc -Destination (Join-Path $vendorPlan 'bob-plan.exe')" not in common


def test_fr9468_tray_plan_uses_planagent_not_vendor_bob_plan():
    """FR #9271: TipForm Plan starts plan\\PlanAgent.exe; Priority stays on vendor\\priority."""
    cs = TRAY.read_text(encoding="utf-8-sig")
    ps = WATCH.read_text(encoding="utf-8-sig")
    assert "vendor\\plan\\bob-plan.exe" not in cs
    assert "vendor\\priority\\PriorityAgent.exe" in cs
    assert "vendor\\plan\\bob-plan.exe" not in ps
    assert "vendor\\priority\\PriorityAgent.exe" in ps
    assert "plan\\PlanAgent.exe" in ps or '"plan", "PlanAgent.exe"' in cs


def test_fr9468_docs_name_release_sources():
    t49 = EVIDENCE49.read_text(encoding="utf-8")
    t55 = EVIDENCE55.read_text(encoding="utf-8")
    assert "9468" in t49 or "9598" in t49
    assert "vendor/plan/PlanAgent.exe" in t49.replace("\\", "/")
    assert "bob-plan.exe" not in t49 or "must not" in t49.lower() or "never" in t49.lower() or "9598" in t49
    assert "skills-visionary" in t49.lower()
    assert "9468" in t55
    assert "vendor/priority/PriorityAgent.exe" in t55.replace("\\", "/")
    assert "priority-mcp" in t55.lower()


def test_fr9468_copy_helper_stages_vendor_exes(tmp_path: Path):
    """Offline: Copy-BobTrayVendorExes mirrors plan/priority into vendor PlanAgent + PriorityAgent only."""
    root = tmp_path / "install"
    plan_dir = root / "plan"
    pri_dir = root / "priority"
    plan_dir.mkdir(parents=True)
    pri_dir.mkdir(parents=True)
    (plan_dir / "PlanAgent.exe").write_bytes(b"MZ-plan-stub")
    (pri_dir / "PriorityAgent.exe").write_bytes(b"MZ-pri-stub")
    (plan_dir / "PlanAgent.MANIFEST.json").write_text(
        '{"tag":"plan-v1.0.5","repo":"SimonBarnett/skills-visionary"}\n',
        encoding="utf-8",
    )
    (pri_dir / "PriorityAgent.MANIFEST.json").write_text(
        '{"tag":"launcher-v2.0.0","repo":"SimonBarnett/priority-mcp"}\n',
        encoding="utf-8",
    )
    # Pre-seed legacy twin so helper must remove it (FR #9598).
    vendor_plan = root / "vendor" / "plan"
    vendor_plan.mkdir(parents=True)
    (vendor_plan / "bob-plan.exe").write_bytes(b"MZ-stale-bob-plan")
    (vendor_plan / "bob-plan.exe.sha256").write_text("dead  bob-plan.exe\n", encoding="utf-8")

    ps = f"""
$ErrorActionPreference = 'Stop'
. '{COMMON}'
$r = Copy-BobTrayVendorExes -Root '{root}' -Require
if (-not $r.ok) {{ throw 'helper returned not ok' }}
$pa = Join-Path '{root}' 'vendor\\plan\\PlanAgent.exe'
$pe = Join-Path '{root}' 'vendor\\priority\\PriorityAgent.exe'
$bp = Join-Path '{root}' 'vendor\\plan\\bob-plan.exe'
if (-not (Test-Path -LiteralPath $pa -PathType Leaf)) {{ throw 'missing PlanAgent.exe' }}
if (-not (Test-Path -LiteralPath $pe -PathType Leaf)) {{ throw 'missing PriorityAgent.exe' }}
if (Test-Path -LiteralPath $bp -PathType Leaf) {{ throw 'bob-plan.exe must not be staged' }}
if (-not (Test-Path -LiteralPath (Join-Path '{root}' 'vendor\\plan\\PlanAgent.exe.sha256') -PathType Leaf)) {{
  throw 'missing PlanAgent.exe.sha256'
}}
if (-not (Test-Path -LiteralPath (Join-Path '{root}' 'vendor\\priority\\PriorityAgent.exe.sha256') -PathType Leaf)) {{
  throw 'missing PriorityAgent.exe.sha256'
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
    assert (root / "vendor" / "plan" / "PlanAgent.exe").is_file()
    assert not (root / "vendor" / "plan" / "bob-plan.exe").exists()
    assert (root / "vendor" / "priority" / "PriorityAgent.exe").is_file()


def test_fr9468_copy_helper_require_throws_when_sources_missing(tmp_path: Path):
    root = tmp_path / "empty"
    root.mkdir()
    ps = f"""
$ErrorActionPreference = 'Stop'
. '{COMMON}'
try {{
  Copy-BobTrayVendorExes -Root '{root}' -Require | Out-Null
  throw 'expected throw'
}} catch {{
  if ($_.Exception.Message -notmatch '9468') {{ throw $_ }}
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
