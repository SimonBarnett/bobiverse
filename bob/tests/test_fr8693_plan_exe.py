"""FR #8693 / BOB-44: Agents > Plan starts vendor bob-plan.exe."""
from repo_layout import REPO

TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"


def test_plan_click_starts_vendor_exe_not_worker_mode():
    cs = TRAY.read_text(encoding="utf-8-sig")
    ps = WATCH.read_text(encoding="utf-8-sig")
    plan = cs.split('new ToolStripMenuItem("Plan")', 1)[1].split('new ToolStripMenuItem("Priority")', 1)[0]
    assert "StartPlanExe();" in plan
    assert 'vendor\\plan\\bob-plan.exe' in cs
    assert 'StartWorker("plan"' not in cs
    click = ps.split("$miPlan.Add_Click({", 1)[1].split("$miPriority.Add_Click({", 1)[0]
    assert "Start-BobTrayPlanExe" in click
    assert "vendor\\plan\\bob-plan.exe" in ps
    assert "bob-worker --mode plan" in ps
    assert "-Mode 'plan'" not in ps.split("function Start-BobTrayPlanExe", 1)[1].split("function Start-BobTrayWorkerExe", 1)[0]
