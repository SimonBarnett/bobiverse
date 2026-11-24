# -*- coding: utf-8 -*-
"""FR #9468 / FR #9598: Pack/Sync stage vendor\\plan\\PlanAgent.exe + vendor\\priority\\PriorityAgent.exe."""
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
    assert "bob-plan.exe" in pack  # fail-closed ban of dual-vendor
    assert "must not dual-vendor" in pack or "PlanAgent.exe only" in pack
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
    assert "vendor\\plan\\PlanAgent.exe" in common or "PlanAgent.exe" in common
    assert "9598" in common
    # FR #9598: helper must not copy bob-plan.exe anymore.
    plan_block = common.split("function Copy-BobTrayVendorExes", 1)[1].split(
        "function Sync-BobiverseAgentFolders", 1
    )[0]
    assert "bob-plan.exe" not in plan_block or "do not dual-stage bob-plan.exe" in plan_block
    assert "Copy-Item -LiteralPath $planSrc -Destination (Join-Path $vendorPlan 'bob-plan.exe')" not in plan_block


def test_fr9468_tray_still_resolves_planagent():
    """FR #9271 / #9598: TipForm Plan starts plan\\PlanAgent.exe (not vendor bob-plan)."""
    cs = TRAY.read_text(encoding="utf-8-sig")
    ps = WATCH.read_text(encoding="utf-8-sig")
    body = cs.split("void StartPlanExe()", 1)[1].split("void StartWorker(", 1)[0]
    assert '"plan", "PlanAgent.exe"' in body
    assert "bob-plan.exe" not in body
    fn = ps.split("function Start-BobTrayPlanExe {", 1)[1].split(
        "function Start-BobTrayWorkerExe {", 1
    )[0]
    assert "plan\\PlanAgent.exe" in fn
    assert "bob-plan.exe" not in fn
    assert "vendor\\priority\\PriorityAgent.exe" in cs
    assert "vendor\\priority\\PriorityAgent.exe" in ps


def test_fr9468_docs_name_release_sources():
    t49 = EVIDENCE49.read_text(encoding="utf-8")
    t55 = EVIDENCE55.read_text(encoding="utf-8")
    assert "9468" in t49
    assert "9598" in t49
    assert "vendor/plan/PlanAgent.exe" in t49.replace("\\", "/")
    assert "vendor/plan/bob-plan.exe" not in t49.replace("\\", "/") or "do not stage" in t49.lower()
    assert "skills-visionary" in t49.lower()
    assert "9468" in t55
    assert "vendor/priority/PriorityAgent.exe" in t55.replace("\\", "/")
    assert "priority-mcp" in t55.lower()


def test_fr9468_copy_helper_stages_vendor_exes(tmp_path: Path):
    """Offline: Copy-BobTrayVendorExes mirrors plan/priority into tray vendor paths + sha256."""
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
if (Test-Path -LiteralPath $bp -PathType Leaf) {{ throw 'unexpected bob-plan.exe dual-vendor' }}
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
    assert not (root / "vendor" / "plan" / "bob-plan.exe").is_file()
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
