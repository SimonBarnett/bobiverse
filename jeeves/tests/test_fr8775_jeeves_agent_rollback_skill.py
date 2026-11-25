"""FR #8775: bobiverse-jeeves-agent-rollback skill DAG node + hard rules."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import REPO, ROOT

SKILL = REPO / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-agent-rollback" / "SKILL.md"
JEEVES_SKILLS = REPO / "jeeves" / ".grok" / "skills"
COMMON_SKILLS = REPO / "common" / ".grok" / "skills"
MCP = REPO / "bob" / "scripts" / "skill_dag_mcp.py"
INDEX = REPO / "bob" / "scripts" / "skill_dag_index.py"

SEED = "bobiverse-jeeves-agent-rollback"
CLOSURE = frozenset(
    {
        "bobiverse-jeeves-agent-rollback",
        "bobiverse-jeeves-agent-install",
        "bobiverse-jeeves-agent-build",
        "bobiverse-jeeves-agent-monitor",
        "bobiverse-build",
        # install depends_on winrm (fleet PSRemoting precondition).
        "bobiverse-jeeves-agent-winrm",
    }
)
DEPS = (
    "bobiverse-jeeves-agent-monitor",
    "bobiverse-jeeves-agent-install",
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
    "build-locks.json",
    "ROLLBACK.ps1",
    "bobiverse-jeeves-agent-monitor",
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
    # FR #8775 / MRB #8826: Windows autocrlf checks out LF blobs as CRLF.
    # Normalize before ASCII/content pins; refuse BOM only.
    text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return text


def test_fr8775_skill_path_name_and_frontmatter():
    assert SKILL.is_file()
    t = _utf8(SKILL)
    assert t.startswith("---\n")
    assert re.search(r"^name: bobiverse-jeeves-agent-rollback\n", t, re.M)
    assert SKILL.parent.name == "bobiverse-jeeves-agent-rollback"
    for dep in DEPS:
        assert f"- {dep}" in t
    # CAST IRON before first ##
    iron = t.index(CAST_IRON)
    first_h2 = t.find("\n## ")
    assert first_h2 > 0 and iron < first_h2
    for mk in HARVEST_MARKS:
        assert mk in t, mk
    # ASCII only
    assert all(ord(ch) < 128 for ch in t), "non-ASCII in skill"
    for host in ("bob.ntsa.uk", "irc.ntsa.uk", "github.com"):
        assert host in t or host == "github.com"  # github optional in body
    assert "bob.ntsa.uk" in t
    assert "C:\\Users\\Administrator\\.jeeves" in t  # chair home path (public ops path)
    assert "C:\\Users\\Administrator\\AppData" not in t
    for rule in HARD_RULES:
        assert rule in t, rule
    assert "!resync" not in t.lower() or "do **not** run `!resync`" in t.lower()
    assert "do **not** run `!resync`" in t.lower() or "Do **not** run `!resync`" in t


def test_fr8775_dag_closure_via_mcp_server():
    sys.path.insert(0, str(REPO / "bob" / "scripts"))
    import skill_dag_index as idx  # noqa: E402
    import skill_dag_mcp as mcp  # noqa: E402

    roots = [JEEVES_SKILLS, COMMON_SKILLS]
    server = mcp.SkillDagServer(roots=roots)
    # Every declared dependency in the reachable set must exist as a node
    out = server.resolve(SEED)
    matched_ids = [n["id"] for n in out["matched"]]
    assert matched_ids[0] == SEED
    assert set(matched_ids) == CLOSURE
    assert not (out.get("skipped") or [])
    for node_id in CLOSURE:
        assert node_id in server.nodes, node_id
        for dep in server.nodes[node_id].get("depends_on") or []:
            assert dep in server.nodes, (node_id, dep)
    # Implementation collisions list empty (cross-root bobiverse-build is known; do not assert it)
    collisions = getattr(server, "collisions", None)
    if collisions is not None:
        assert collisions == [] or collisions == {}
    # Force index write detects no cycle
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        index_path = Path(td) / "skill-dag-index.json"
        rc = idx.build_index(roots=roots, index_path=index_path, force=True)
        assert rc == 0
        data = json.loads(index_path.read_text(encoding="utf-8"))
        assert SEED in (data.get("nodes") or data) or SEED in str(data)


def test_fr8775_cli_resolve_seed():
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
