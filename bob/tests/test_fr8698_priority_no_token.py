"""FR #8698 / BOB-52: Priority quits when this box's fuel file is empty."""
import json
import subprocess
from pathlib import Path

from repo_layout import REPO

TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
EMPTY = REPO / "bob" / "tests" / "fixtures" / "priority-fuel-empty.json"
OK = REPO / "bob" / "tests" / "fixtures" / "priority-fuel-ok.json"
EVIDENCE = REPO / "bob" / "docs" / "bob-52-priority-no-token-evidence.md"


def test_fuel_empty_fixture_is_zero():
    doc = json.loads(EMPTY.read_text(encoding="utf-8"))
    assert int(doc["remaining_pct"]) == 0
    assert doc["status"] == "empty"


def test_evidence_doc_pins_s1():
    text = EVIDENCE.read_text(encoding="utf-8")
    assert "BOB-52" in text
    assert "no-token" in text.lower() or "no token" in text.lower()
    assert "quit" in text.lower()


def test_clicks_quit_before_priority_start():
    cs = TRAY.read_text(encoding="utf-8-sig")
    ps = WATCH.read_text(encoding="utf-8-sig")
    # FR #9269: flat miPriority.Click (no Start PriorityAgent submenu).
    i = cs.find("miPriority.Click")
    assert i > 0
    j = cs.find("miAgents.DropDownItems.Add(miPriority)", i)
    assert j > i
    block = cs[i:j]
    assert "PriorityFuelEmpty" in block
    assert block.find("PriorityFuelEmpty") < block.find("StartPriorityExe()")
    assert "return;" in block
    a = ps.find("$miPriority.Add_Click({")
    assert a > 0
    b = ps.find("$miJeeves.Add_Click({", a)
    block_ps = ps[a:b]
    assert block_ps.find("Test-BobTrayPriorityFuelEmpty") < block_ps.find("Start-BobTrayPriorityExe")
    assert "return" in block_ps


def test_fuel_empty_fixture_is_empty_and_ok_is_not():
    watch = WATCH.read_text(encoding="utf-8-sig")
    start = watch.find("function Test-BobTrayPriorityFuelEmpty {")
    assert start > 0
    end = watch.find("\nfunction ", start + 10)
    fn = watch[start:end]
    script = fn + "\n" + (
        "if (Test-BobTrayPriorityFuelEmpty -FuelPath '%s') { 'EMPTY' } else { 'EMPTY_ALLOWED' }\n"
        "if (Test-BobTrayPriorityFuelEmpty -FuelPath '%s') { 'OK_BLOCKED' } else { 'OK_START' }\n"
        "if (Test-BobTrayPriorityFuelEmpty -FuelPath '%s') { 'MISS_BLOCKED' } else { 'MISS_START' }\n"
    ) % (str(EMPTY), str(OK), str(EMPTY.parent / "missing-priority-fuel.json"))
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
