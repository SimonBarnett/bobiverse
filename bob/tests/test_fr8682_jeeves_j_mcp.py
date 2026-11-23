"""FR #8682 / BOB-38: Agents > Jeeves loads skills from J: MCP."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from repo_layout import REPO

TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
HELPER = REPO / "bob" / "tray" / "dialogs" / "JeevesJMcp.cs"
BUILD = REPO / "bob" / "scripts" / "Build-BobDialogs.ps1"
SCRIPTS = REPO / "bob" / "scripts"


def _fn(text: str, start: str, end: str) -> str:
    i = text.find(start)
    assert i >= 0, start
    j = text.find(end, i)
    assert j > i
    return text[i:j]


def test_tray_logs_jeeves_mcp_j_path_before_start():
    cs = TRAY.read_text(encoding="utf-8-sig")
    block = _fn(cs, 'ToolStripMenuItem miJeeves', "menu.Items.Add(miAgents)")
    mcp = block.find("jeeves-mcp")
    start = block.find('StartWorker("agent", "grok"')
    assert 0 <= mcp < start
    assert "JeevesJMcp.DryRunLine" in block
    assert "JeevesJMcp.EnvName" in block and "JeevesJMcp.SkillsRoot" in block
    assert r"J:\.grok\skills" in HELPER.read_text(encoding="utf-8-sig")
    assert "JeevesJMcp.cs" in BUILD.read_text(encoding="utf-8-sig")
    ps = _fn(WATCH.read_text(encoding="utf-8-sig"), "$miJeeves.Add_Click", "$miWeights.Add_Click")
    assert "jeeves-mcp path=J:" in ps
    fn = _fn(WATCH.read_text(encoding="utf-8-sig"), "function Start-BobTrayWorkerExe {", "function Start-BobTrayWorkerAgentsRefresh {")
    assert "BOB_JEEVES_MCP_ROOT" in fn
    assert "jeeves-menu" in fn


def test_mcp_config_and_vision_roots_prefer_j_path(monkeypatch):
    sys.path.insert(0, str(SCRIPTS))
    import jeeves_j_mcp as jm
    import bob_worker as bw

    assert jm.dry_run_line().startswith("jeeves-mcp path=J:")
    doc = jm.mcp_config_document()
    args = doc["mcpServers"]["skill-dag"]["args"]
    assert "--root" in args
    assert args[args.index("--root") + 1] == r"J:\.grok\skills"

    monkeypatch.setenv("BOB_JEEVES_MCP_ROOT", r"J:\.grok\skills")
    roots = bw.skill_dag_vision_roots(str(REPO / "bob" / "worker"))
    assert roots[0] == Path(r"J:\.grok\skills")
