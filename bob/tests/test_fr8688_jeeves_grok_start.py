"""FR #8688 / BOB-33: Agents > Jeeves starts Grok Build and logs it."""
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


def test_compiled_jeeves_click_logs_grok_start_and_launches():
    src = TRAY.read_text(encoding="utf-8-sig")
    block = _fn(src, 'ToolStripMenuItem miJeeves', "menu.Items.Add(miAgents)")
    assert 'action", "grok start"' in block
    assert 'StartWorker("agent", "grok")' in block


def test_ps_jeeves_click_logs_grok_start_and_launches():
    src = WATCH.read_text(encoding="utf-8-sig")
    block = _fn(src, "$miJeeves.Add_Click", "$miWeights.Add_Click")
    assert "Jeeves: grok start" in block
    assert "-Mode 'agent'" in block and "-Agent 'grok'" in block
    assert "jeeves-menu" in block
