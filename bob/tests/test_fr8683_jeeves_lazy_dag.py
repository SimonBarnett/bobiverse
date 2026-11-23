"""FR #8683 / BOB-39: Agents > Jeeves lazy-load skill DAG."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from repo_layout import REPO

TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
HELPER = REPO / "bob" / "tray" / "dialogs" / "JeevesLazyDag.cs"
SMOKE = REPO / "bob" / "scripts" / "jeeves_lazy_dag.py"
BUILD = REPO / "bob" / "scripts" / "Build-BobDialogs.ps1"


def _fn(text: str, start: str, end: str) -> str:
    i = text.find(start)
    assert i >= 0, start
    j = text.find(end, i)
    assert j > i
    return text[i:j]


def test_tray_logs_jeeves_dag_lazy_before_start():
    cs = TRAY.read_text(encoding="utf-8-sig")
    block = _fn(cs, 'ToolStripMenuItem miJeeves', "menu.Items.Add(miAgents)")
    lazy = block.find("jeeves-dag")
    start = block.find('StartWorker("agent", "grok"')
    assert 0 <= lazy < start
    assert "JeevesLazyDag.DryRunLine" in block
    assert "JeevesLazyDag.cs" in BUILD.read_text(encoding="utf-8-sig")
    assert "jeeves-dag lazy root=" in HELPER.read_text(encoding="utf-8-sig")
    ps = _fn(WATCH.read_text(encoding="utf-8-sig"), "$miJeeves.Add_Click", "$miWeights.Add_Click")
    assert "jeeves-dag lazy root=" in ps
    assert ps.find("jeeves-dag lazy") < ps.find("Jeeves: grok start")


def test_lazy_dag_smoke_indexes_without_eager_bodies(tmp_path: Path):
    root = tmp_path / ".grok" / "skills"
    a = root / "alpha"
    b = root / "beta"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    (a / "SKILL.md").write_text(
        "---\nname: alpha\ndescription: first\ndepends_on: []\n---\n\n# Alpha\n" + ("x" * 200),
        encoding="utf-8",
    )
    (b / "SKILL.md").write_text(
        "---\nname: beta\ndescription: second\ndepends_on: [alpha]\n---\n\n# Beta\n" + ("y" * 200),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(SMOKE), "--skills-root", str(root), "--json"],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(SMOKE.parent),
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["mode"] == "lazy"
    assert data["nodes"] == 2
    assert data["line"].startswith("jeeves-dag lazy nodes=2")
    # Slim payload: ids/paths/bytes only — no body text from SKILL.md.
    blob = json.dumps(data)
    assert "xxxxx" not in blob and "yyyyy" not in blob
