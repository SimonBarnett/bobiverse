"""FR #9271 / BOB-TRAY-UI-10 (+ FR #9605): Agents > Plan click starts vendor\\plan\\PlanAgent.exe."""
from __future__ import annotations

from repo_layout import REPO

TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
README = REPO / "bob" / "agents" / "plan" / "README.md"
EVIDENCE = REPO / "bob" / "docs" / "fr-8693-plan-exe-evidence.md"


def test_fr9271_plan_click_wires_start_plan_exe():
    cs = TRAY.read_text(encoding="utf-8-sig")
    plan = cs.split('new ToolStripMenuItem("Plan")', 1)[1].split('new ToolStripMenuItem("Priority")', 1)[0]
    assert "miPlan.Click" in plan
    assert "StartPlanExe();" in plan
    assert "miPlan.DropDownItems" not in plan
    assert 'MenuItems.Add("Plan")' in plan


def test_fr9271_start_plan_exe_uses_planagent_not_bob_plan():
    cs = TRAY.read_text(encoding="utf-8-sig")
    body = cs.split("void StartPlanExe()", 1)[1].split("void StartWorker(", 1)[0]
    # FR #9605: tray starts the Pack/Sync vendor mirror (live installs often lack plan\).
    assert '"vendor", "plan", "PlanAgent.exe"' in body
    assert "bob-plan.exe" not in body
    assert "start exe missing" in body
    assert "Plan - missing exe" in body
    assert 'via", "bob-tray-Plan"' in body


def test_fr9271_ps_start_uses_planagent():
    ps = WATCH.read_text(encoding="utf-8-sig")
    fn = ps.split("function Start-BobTrayPlanExe {", 1)[1].split("function Start-BobTrayWorkerExe {", 1)[0]
    assert "vendor\\plan\\PlanAgent.exe" in fn
    assert "bob-plan.exe" not in fn
    assert "Plan - missing exe" in fn
    click = ps.split("$miPlan.Add_Click({", 1)[1].split("$miPriority.Add_Click({", 1)[0]
    assert "Start-BobTrayPlanExe" in click


def test_fr9271_docs_agree_with_msi_planagent():
    readme = README.read_text(encoding="utf-8")
    assert "vendor\\plan\\PlanAgent.exe" in readme or "vendor/plan/PlanAgent.exe" in readme
    ev = EVIDENCE.read_text(encoding="utf-8")
    assert "PlanAgent.exe" in ev
    assert "9271" in ev or "BOB-TRAY-UI-10" in ev or "9605" in ev
