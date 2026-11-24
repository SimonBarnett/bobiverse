"""FR #9641: Agents > Plan starts PlanAgent.exe; Pack refuses bob-worker bytes as PlanAgent."""
from __future__ import annotations

from repo_layout import REPO

TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
COMMON = REPO / "common" / "scripts" / "Bobiverse-Common.ps1"
PACK = REPO / "common" / "scripts" / "Pack-BobiverseRelease.ps1"


def test_fr9641_tipform_plan_click_is_startplanexe_not_startworker():
    cs = TRAY.read_text(encoding="utf-8-sig")
    # Agents > Plan click must call StartPlanExe only (never StartWorker("plan")).
    assert 'ToolStripMenuItem miPlan = new ToolStripMenuItem("Plan");' in cs
    window = cs.split('ToolStripMenuItem miPlan = new ToolStripMenuItem("Plan");', 1)[1]
    window = window.split("miAgents.DropDownItems.Add(miPlan);", 1)[0]
    assert "StartPlanExe();" in window
    assert 'StartWorker("plan"' not in window
    assert "StartWorker(" not in window
    # Comment immediately above StartPlanExe cites no bob-worker --mode plan.
    before = cs.split("void StartPlanExe()", 1)[0][-400:]
    assert "Not bob-worker --mode plan" in before or "not bob-worker" in before.lower()
    body = cs.split("void StartPlanExe()", 1)[1].split("void StartWorker(", 1)[0]
    assert '"vendor", "plan", "PlanAgent.exe"' in body
    assert 'StartWorker("plan"' not in body
    assert "bob-worker.exe" not in body


def test_fr9641_watch_plan_not_worker_mode():
    ps = WATCH.read_text(encoding="utf-8-sig")
    fn = ps.split("function Start-BobTrayPlanExe {", 1)[1].split("function Start-BobTrayWorkerExe {", 1)[0]
    assert "vendor\\plan\\PlanAgent.exe" in fn
    assert "Do not fall back to bob-worker" in fn
    # Must not invoke bob-worker; comment may mention --mode plan as forbidden fallback.
    assert "bob-worker.exe" not in fn
    assert "Start-BobTrayWorkerExe" not in fn


def test_fr9641_assert_helper_and_pack_wire():
    common = COMMON.read_text(encoding="utf-8-sig")
    assert "function Assert-BobiversePlanAgentNotBobWorker" in common
    assert "FR #9641" in common
    assert "matches worker\\bob-worker.exe" in common
    copy_fn = common.split("function Copy-BobTrayVendorExes {", 1)[1].split(
        "function Assert-BobiversePlanAgentNotBobWorker {", 1
    )[0]
    assert "Assert-BobiversePlanAgentNotBobWorker" in copy_fn
    pack = PACK.read_text(encoding="utf-8-sig")
    assert "Assert-BobiversePlanAgentNotBobWorker -Root $Stage -Require" in pack
    assert "FR #9641" in pack


def test_fr9641_assert_throws_when_plan_hash_equals_worker(tmp_path):
    """Offline: identical PlanAgent/worker bytes fail closed under -Require."""
    import subprocess

    root = tmp_path / "install"
    (root / "vendor" / "plan").mkdir(parents=True)
    (root / "worker").mkdir(parents=True)
    twin = b"MZ-identical-worker-as-plan"
    (root / "vendor" / "plan" / "PlanAgent.exe").write_bytes(twin)
    (root / "worker" / "bob-worker.exe").write_bytes(twin)
    common = COMMON
    ps = f"""
. '{common}'
try {{
  Assert-BobiversePlanAgentNotBobWorker -Root '{root}' -Require
  exit 0
}} catch {{
  if ($_.Exception.Message -match 'FR #9641') {{ exit 42 }}
  Write-Error $_
  exit 1
}}
"""
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert r.returncode == 42, (r.returncode, r.stdout, r.stderr)
