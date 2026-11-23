"""FR #8679 / BOB-37: Agents > Jeeves starts with cwd J: (mapped to ai\\jeeves)."""
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


def test_compiled_jeeves_click_logs_cwd_j_before_start():
    src = TRAY.read_text(encoding="utf-8-sig")
    block = _fn(src, 'ToolStripMenuItem miJeeves', "menu.Items.Add(miAgents)")
    cwd = block.find("cwd J:")
    start = block.find('StartWorker("agent", "grok"')
    assert 0 <= cwd < start
    assert '@"J:\\"' in block


def test_ps_jeeves_click_logs_cwd_j_and_sets_wd():
    src = WATCH.read_text(encoding="utf-8-sig")
    block = _fn(src, "$miJeeves.Add_Click", "$miWeights.Add_Click")
    assert "cwd J:" in block
    fn = _fn(src, "function Start-BobTrayWorkerExe {", "function Start-BobTrayWorkerAgentsRefresh {")
    assert "jeeves-menu" in fn
    assert "J:\\" in fn
