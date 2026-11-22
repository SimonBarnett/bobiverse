"""FR #8693 / BOB-44: Agents > Plan starts vendor bob-plan.exe."""
from repo_layout import REPO

TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"


def test_plan_click_starts_vendor_exe_not_worker_mode():
    cs = TRAY.read_text(encoding="utf-8-sig")
    ps = WATCH.read_text(encoding="utf-8-sig")
    assert 'miPlan.Click += delegate { StartPlanExe(); }' in cs
    assert 'vendor\\plan\\bob-plan.exe' in cs
    assert 'StartWorker("plan"' not in cs
    assert "$miPlan.Add_Click({ Start-BobTrayPlanExe })" in ps
    assert "vendor\\plan\\bob-plan.exe" in ps
    assert "bob-worker --mode plan" in ps
    assert "-Mode 'plan'" not in ps.split("function Start-BobTrayPlanExe", 1)[1].split("function Start-BobTrayWorkerExe", 1)[0]
