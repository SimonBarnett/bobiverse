"""FR #8692 / BOB-46: Plan quits when this box's fuel file is empty."""
import json
import subprocess
from pathlib import Path

from repo_layout import REPO

TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
EMPTY = REPO / "bob" / "tests" / "fixtures" / "plan-fuel-empty.json"
OK = REPO / "bob" / "tests" / "fixtures" / "plan-fuel-ok.json"


def test_fuel_empty_fixture_is_zero():
    doc = json.loads(EMPTY.read_text(encoding="utf-8"))
    assert int(doc["remaining_pct"]) == 0
    assert doc["status"] == "empty"


def test_clicks_quit_before_plan_start():
    cs = TRAY.read_text(encoding="utf-8-sig")
    ps = WATCH.read_text(encoding="utf-8-sig")
    i = cs.find('new ToolStripMenuItem("Plan")')
    j = cs.find('new ToolStripMenuItem("Priority")', i)
    click = cs[i:j]
    assert click.find("PlanFuelEmpty") < click.find("StartPlanExe()")
    assert "return;" in click
    a = ps.find("$miPlan.Add_Click({")
    b = ps.find("$miPriority.Add_Click({", a)
    block = ps[a:b]
    assert block.find("Test-BobTrayPlanFuelEmpty") < block.find("Start-BobTrayPlanExe")
    assert "return" in block


def test_fuel_empty_fixture_is_empty_and_ok_is_not():
    watch = WATCH.read_text(encoding="utf-8-sig")
    start = watch.find("function Test-BobTrayPlanFuelEmpty {")
    end = watch.find("function Start-BobTrayPlanExe {", start)
    fn = watch[start:end]
    script = fn + "\n" + (
        "if (Test-BobTrayPlanFuelEmpty -FuelPath '%s') { 'EMPTY' } else { 'EMPTY_ALLOWED' }\n"
        "if (Test-BobTrayPlanFuelEmpty -FuelPath '%s') { 'OK_BLOCKED' } else { 'OK_START' }\n"
        "if (Test-BobTrayPlanFuelEmpty -FuelPath '%s') { 'MISS_BLOCKED' } else { 'MISS_START' }\n"
    ) % (str(EMPTY), str(OK), str(EMPTY.parent / "missing-plan-fuel.json"))
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "EMPTY" in out and "EMPTY_ALLOWED" not in out
    assert "OK_START" in out and "OK_BLOCKED" not in out
    assert "MISS_START" in out
