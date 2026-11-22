"""FR #8721 / BOB-21: Workers > Cursor starts Cursor CLI; cursor-agent: log evidence."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from repo_layout import REPO, ROOT

TRAY_CS = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
WORKER = REPO / "bob" / "scripts" / "bob_worker.py"
DOCS = REPO / "bob" / "docs" / "bob-tray-dialogs.md"
SCRIPTS = REPO / "bob" / "scripts"
TESTS = REPO / "bob" / "tests"


def test_fr8721_workers_cursor_menu_wiring_both_trays():
    cs = TRAY_CS.read_text(encoding="utf-8-sig")
    w = WATCH.read_text(encoding="utf-8-sig")
    # BOB-06 tree: Cursor under Workers, not Agents product rows
    i_workers = cs.index('new ToolStripMenuItem("Workers")')
    i_cursor = cs.index('AddAgentChoice(parent, "cursor", "Cursor"')
    assert i_workers < i_cursor
    seed = cs[cs.index("void SeedAgentChoices") : cs.index("void SeedAgentChoices") + 1200]
    assert 'AddAgentChoice(parent, "cursor", "Cursor"' in seed
    assert "OnAgentChoiceClick" in cs
    assert 'StartWorker("agent"' in cs or 'StartWorker("agent",' in cs
    # PS tray seeds cursor under Workers
    assert "Update-BobTrayWorkerAgentsMenu $miWorkers" in w
    assert "[ordered]@{ id = 'cursor'; label = 'Cursor'" in w
    opening = w[w.index("$miWorkers.Add_DropDownOpening") : w.index("$miWorkers.Add_DropDownOpening") + 500]
    assert "Start-BobTrayWorkerAgentsRefresh $miWorkers" in opening
    # cursor-agent S1 log token
    src = WORKER.read_text(encoding="utf-8")
    assert "cursor-agent:" in src
    assert "resolve_cursor_cmd" in src
    assert "Workers > Cursor" in DOCS.read_text(encoding="utf-8") or "Workers" in DOCS.read_text(encoding="utf-8")


def test_fr8721_cursor_agent_log_after_successful_spawn(tmp_path, monkeypatch):
    sys.path.insert(0, str(SCRIPTS))
    sys.path.insert(0, str(TESTS))
    import bob_worker as bw
    import test_bob_worker_020 as t020

    monkeypatch.setattr(bw, "resolve_cursor_cmd", lambda env=None, which=None: r"C:\x\agent.cmd")
    (tmp_path / "run").mkdir()
    rig = t020.Rig(tmp_path, kind="cursor")
    assert rig.sup.start_agent()
    hits = [L for L in rig.logs if L.startswith("cursor-agent:")]
    assert len(hits) == 1
    line = hits[0]
    assert "cmd=C:\\x\\agent.cmd" in line or "cmd=C:/x/agent.cmd" in line.replace("\\", "/")
    assert f"pid={rig.procs[0].pid}" in line
    assert "nick=marchhare-4242" in line
    assert "workspace=" in line


def test_fr8721_cursor_agent_log_absent_when_spawn_fails(tmp_path, monkeypatch):
    sys.path.insert(0, str(SCRIPTS))
    sys.path.insert(0, str(TESTS))
    import bob_worker as bw
    import test_bob_worker_020 as t020

    monkeypatch.setattr(bw, "resolve_cursor_cmd", lambda env=None, which=None: None)

    def boom(spec, env):
        raise OSError("no agent.cmd")

    (tmp_path / "run").mkdir()
    rig = t020.Rig(tmp_path, kind="cursor")
    rig.sup.spawn = boom
    assert rig.sup.start_agent() is False
    assert not any(L.startswith("cursor-agent:") for L in rig.logs)


def test_fr8721_dump_menu_workers_precedes_cursor():
    """Source contract: MenuItems records Workers before Cursor (matches --dump-menu)."""
    cs = TRAY_CS.read_text(encoding="utf-8-sig")
    i_w = cs.index('MenuItems.Add("Workers")')
    seed = cs[cs.index("void SeedAgentChoices") : cs.index("void AddAgentChoice")]
    assert 'AddAgentChoice(parent, "cursor", "Cursor", true, record)' in seed
    i_add = cs.index('AddAgentChoice(parent, "cursor", "Cursor", true, record)')
    assert i_w < i_add
