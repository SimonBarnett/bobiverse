"""FR #8780: bobiverse-jeeves-agent-main-red skill DAG node + hard rules."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from repo_layout import REPO, ROOT

SKILL = REPO / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-agent-main-red" / "SKILL.md"
JEEVES_SKILLS = REPO / "jeeves" / ".grok" / "skills"
COMMON_SKILLS = REPO / "common" / ".grok" / "skills"
MCP = REPO / "bob" / "scripts" / "skill_dag_mcp.py"

SEED = "bobiverse-jeeves-agent-main-red"
CLOSURE = frozenset(
    {
        "bobiverse-jeeves-agent-main-red",
        "bobiverse-jeeves-agent-build",
        "bobiverse-jeeves-agent-monitor",
        "bobiverse-build",
    }
)
DEPS = (
    "bobiverse-jeeves-agent-build",
)
HARD_RULES = (
    "No secrets",
    "Never edit the Jeeves ledger",
    "queue.json",
    "no fake `ACK`",
    "!build cancel",
    "ErgoWalrus",
    "Never restart Jeeves while a build runs",
    "One machine at a time",
)
CAST_IRON = "CAST IRON RULE - HARVEST AND FILE EVERYTHING"
HARVEST_MARKS = (
    "Report-BobiverseIntakeIssue.ps1",
    "Invoke-BobiverseHarvest.ps1",
    "https://bob.ntsa.uk/bob/v1/intake",
    "-Repo SimonBarnett/bobiverse",
)


def _utf8(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), f"BOM in {path}"
    return raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


def test_fr8780_skill_path_name_and_frontmatter():
    assert SKILL.is_file()
    t = _utf8(SKILL)
    assert t.startswith("---\n")
    assert re.search(r"^name: bobiverse-jeeves-agent-main-red\n", t, re.M)
    assert SKILL.parent.name == SEED
    for dep in DEPS:
        assert f"- {dep}" in t
    iron = t.index(CAST_IRON)
    first_h2 = t.find("\n## ")
    assert first_h2 > 0 and iron < first_h2
    for mk in HARVEST_MARKS:
        assert mk in t, mk
    assert all(ord(ch) < 128 for ch in t), "non-ASCII in skill"
    assert "bob.ntsa.uk" in t
    assert "irc.ntsa.uk" in t or "github.com" in t
    assert "C:\\Users\\Administrator\\AppData" not in t
    for rule in HARD_RULES:
        assert rule in t, rule
    assert "build-jeeves" in t
    assert "last green" in t
    assert "first bad" in t
    assert "MarchHare" in t
    assert "44909235948" in t


def test_fr8780_dag_closure_via_mcp_server():
    sys.path.insert(0, str(REPO / "bob" / "scripts"))
    import skill_dag_index as idx  # noqa: E402
    import skill_dag_mcp as mcp  # noqa: E402

    roots = [JEEVES_SKILLS, COMMON_SKILLS]
    server = mcp.SkillDagServer(roots=roots)
    out = server.resolve(SEED)
    matched_ids = [n["id"] for n in out["matched"]]
    assert matched_ids[0] == SEED
    assert set(matched_ids) == CLOSURE
    assert not (out.get("skipped") or [])
    for node_id in CLOSURE:
        assert node_id in server.nodes, node_id
        for dep in server.nodes[node_id].get("depends_on") or []:
            assert dep in server.nodes, (node_id, dep)
    with tempfile.TemporaryDirectory() as td:
        index_path = Path(td) / "skill-dag-index.json"
        rc = idx.build_index(roots=roots, index_path=index_path, force=True)
        assert rc == 0


def test_fr8780_cli_resolve_seed():
    assert MCP.is_file()
    cp = subprocess.run(
        [
            sys.executable,
            str(MCP),
            "--root",
            str(JEEVES_SKILLS),
            "--root",
            str(COMMON_SKILLS),
            "--once",
            "resolve",
            "--seed",
            SEED,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert cp.returncode == 0, cp.stderr
    out = json.loads(cp.stdout)
    ids = [n["id"] for n in out["matched"]]
    assert ids[0] == SEED
    assert set(ids) == CLOSURE
    assert not (out.get("skipped") or [])