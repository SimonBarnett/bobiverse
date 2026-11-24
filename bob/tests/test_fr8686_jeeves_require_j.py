"""FR #8686 / BOB-36: Agents > Jeeves quits when J: is not mapped."""
import subprocess
import uuid
from pathlib import Path

from repo_layout import REPO

TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"


def _fn(text: str, start: str, end: str) -> str:
    i = text.find(start)
    assert i >= 0, start
    j = text.find(end, i)
    assert j > i
    return text[i:j]


def test_jeeves_click_quits_before_start_when_j_missing():
    cs = TRAY.read_text(encoding="utf-8-sig")
    ps = WATCH.read_text(encoding="utf-8-sig")
    click = _fn(cs, 'new ToolStripMenuItem("Jeeves")', 'MenuItems.Add("Jeeves")')
    missing = click.find("J: map missing")
    start = click.find('StartWorker("agent", "grok"')
    assert 0 <= missing < start
    assert "return;" in click[missing:start]
    ps_click = _fn(ps, "$miJeeves.Add_Click({", "$miWeights.Add_Click({")
    ps_missing = ps_click.find("J: map missing")
    ps_start = ps_click.find("Start-BobTrayWorkerExe")
    assert 0 <= ps_missing < ps_start
    assert "return" in ps_click[ps_missing:ps_start]


def test_missing_j_fixture_is_not_a_map(tmp_path: Path):
    watch = WATCH.read_text(encoding="utf-8-sig")
    start = watch.find("function Test-BobTrayJeevesDrive {")
    end = watch.find("function Start-BobTrayPriorityExe {", start)
    assert start >= 0 and end > start
    fn = watch[start:end]
    missing = tmp_path / ("no-j-" + uuid.uuid4().hex)
    mapped = tmp_path / "mapped-j"
    mapped.mkdir()
    script = fn + "\n" + (
        "if (Test-BobTrayJeevesDrive -DriveRoot '%s') { 'MISSING_PRESENT' } else { 'MISSING_QUIT' }\n"
        "if (Test-BobTrayJeevesDrive -DriveRoot '%s') { 'MAPPED_OK' } else { 'MAPPED_QUIT' }\n"
    ) % (str(missing), str(mapped))
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "MISSING_QUIT" in out
    assert "MAPPED_OK" in out
    assert "MISSING_PRESENT" not in out
