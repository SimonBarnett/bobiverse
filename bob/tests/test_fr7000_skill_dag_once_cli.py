"""FR #7000: Cursor seats may lack skill-dag MCP; --once CLI is the supported fallback."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from repo_layout import ROOT

MCP = ROOT / "bob" / "scripts" / "skill_dag_mcp.py"
WORKER = ROOT / "bob" / "scripts" / "bob_worker.py"


def test_fr7000_once_resolve_and_get_skill(tmp_path: Path):
    skills = tmp_path / "skills" / "bobiverse-bob-job-fr"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text(
        "---\nname: bobiverse-bob-job-fr\ndescription: fr job\ndepends_on: []\n---\n\n# FR\n",
        encoding="utf-8",
    )
    # JOB_SEEDS maps FR -> bobiverse-bob-job-fr
    r = subprocess.run(
        [
            sys.executable,
            str(MCP),
            "--root",
            str(tmp_path / "skills"),
            "--once",
            "resolve",
            "--seed",
            "FR",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert any(m.get("id") == "bobiverse-bob-job-fr" for m in data.get("matched") or [])
    path = next(m["path"] for m in data["matched"] if m["id"] == "bobiverse-bob-job-fr")
    g = subprocess.run(
        [
            sys.executable,
            str(MCP),
            "--root",
            str(tmp_path / "skills"),
            "--once",
            "get_skill",
            "--path",
            path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert g.returncode == 0, g.stderr
    body = json.loads(g.stdout)
    assert body.get("ok") is True
    assert "# FR" in (body.get("body") or "")


def test_fr7000_worker_prompt_documents_once_fallback():
    text = WORKER.read_text(encoding="utf-8")
    assert "FR #7000" in text
    assert "--once resolve" in text
    assert "skill_dag_mcp.py" in text
