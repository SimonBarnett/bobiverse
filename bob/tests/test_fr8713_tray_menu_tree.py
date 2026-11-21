"""FR #8713 / BOB-06: tray menu tree Status/Agents/Workers/Weights/About/Exit."""
from __future__ import annotations

from repo_layout import ROOT

TRAY = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
EVIDENCE = ROOT / "bob" / "docs" / "bob-06-tray-menu-tree-evidence.md"
MOCK = ROOT / "bob" / "docs" / "mocks" / "systray-agents-workers" / "home.html"


def test_evidence():
    text = EVIDENCE.read_text(encoding="utf-8")
    assert "BOB-06" in text
    assert "Agents" in text
    assert "Workers" in text
    assert "Weights" in text


def test_bob_tray_menu_tree_structure():
    src = TRAY.read_text(encoding="utf-8-sig")
    mock = MOCK.read_text(encoding="utf-8")
    for label in ("Status", "Agents", "Workers", "Weights", "About", "Exit"):
        assert label in mock
        assert f'"{label}"' in src or f"'{label}'" in src
    # Agents children Plan/Priority/Jeeves — Plan not flat top-level Item helper
    stripped = src.replace('ToolStripMenuItem("Plan")', '')
    assert 'Item("Plan"' not in stripped
    assert '"Plan"' in src
    assert '"Priority"' in src
    assert '"Jeeves"' in src
    # Workers submenu owns worker agent seed / refresh
    assert 'new ToolStripMenuItem("Workers")' in src
    assert "SeedAgentChoices(miWorkers" in src
    # Agents no longer seeded with worker choices
    assert "SeedAgentChoices(miAgents" not in src
    i_agents = src.index('new ToolStripMenuItem("Agents")')
    i_workers = src.index('new ToolStripMenuItem("Workers")')
    i_weights = src.index('"Weights"')
    assert i_agents < i_workers < i_weights


def test_tipform_menu_tree_structure():
    text = WATCH.read_text(encoding="utf-8")
    assert "$menu.Items.Add('Plan')" not in text
    assert "Workers" in text
    assert "Weights" in text
    assert "About" in text
    assert "Priority" in text
    assert "Jeeves" in text
