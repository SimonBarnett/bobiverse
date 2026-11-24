# -*- coding: utf-8 -*-
"""FR #9598: stage vendor\\plan\\PlanAgent.exe only; never dual-vendor bob-plan.exe."""
from __future__ import annotations

import subprocess
from pathlib import Path

from repo_layout import ROOT

COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
EVIDENCE49 = ROOT / "bob" / "docs" / "bob-49-bob-ear-msi-include-plan-evidence.md"
TRAY = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"


def test_fr9598_copy_helper_planagent_only(tmp_path: Path):
    root = tmp_path / "install"
    (root / "plan").mkdir(parents=True)
    (root / "priority").mkdir(parents=True)
    (root / "plan" / "PlanAgent.exe").write_bytes(b"MZ-plan")
    (root / "priority" / "PriorityAgent.exe").write_bytes(b"MZ-pri")
    ps = f"""
$ErrorActionPreference = 'Stop'
. '{COMMON}'
Copy-BobTrayVendorExes -Root '{root}' -Require | Out-Null
$pa = Join-Path '{root}' 'vendor\\plan\\PlanAgent.exe'
$bp = Join-Path '{root}' 'vendor\\plan\\bob-plan.exe'
if (-not (Test-Path -LiteralPath $pa -PathType Leaf)) {{ throw 'missing PlanAgent.exe' }}
if (Test-Path -LiteralPath $bp -PathType Leaf) {{ throw 'bob-plan.exe must not be staged' }}
if (-not (Test-Path -LiteralPath (Join-Path '{root}' 'vendor\\plan\\PlanAgent.exe.sha256') -PathType Leaf)) {{
  throw 'missing PlanAgent.exe.sha256'
}}
if (Test-Path -LiteralPath (Join-Path '{root}' 'vendor\\plan\\bob-plan.exe.sha256') -PathType Leaf) {{
  throw 'bob-plan.exe.sha256 must not be staged'
}}
Write-Output 'OK9598'
"""
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    assert "OK9598" in (r.stdout or "")


def test_fr9598_pack_requires_planagent_bans_bob_plan():
    pack = PACK.read_text(encoding="utf-8-sig")
    assert "9598" in pack
    assert r"vendor\plan\PlanAgent.exe" in pack or "vendor\\plan\\PlanAgent.exe" in pack
    assert "must not dual-vendor" in pack
    # Fail-closed require path is PlanAgent, not bob-plan.
    assert "missing vendor\\plan\\PlanAgent.exe" in pack or "missing vendor\\plan\\PlanAgent.exe" in pack.replace(
        "/", "\\"
    )


def test_fr9598_docs_and_tray_agree():
    doc = EVIDENCE49.read_text(encoding="utf-8")
    assert "9598" in doc
    assert "PlanAgent.exe" in doc
    assert "Do not stage `bob-plan.exe`" in doc or "do not stage bob-plan" in doc.lower()
    cs = TRAY.read_text(encoding="utf-8-sig")
    body = cs.split("void StartPlanExe()", 1)[1].split("void StartWorker(", 1)[0]
    assert '"plan", "PlanAgent.exe"' in body
    fn = WATCH.read_text(encoding="utf-8-sig").split("function Start-BobTrayPlanExe {", 1)[1].split(
        "function Start-BobTrayWorkerExe {", 1
    )[0]
    assert "plan\\PlanAgent.exe" in fn
