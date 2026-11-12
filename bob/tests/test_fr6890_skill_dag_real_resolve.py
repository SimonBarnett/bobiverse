"""FR #6890: resolve on real SKILL.md files keeps the job skill."""
from __future__ import annotations

from pathlib import Path

import skill_dag_mcp as mcp

REPO = Path(__file__).resolve().parents[2]
REAL_ROOTS = [
    REPO / "bob" / ".grok" / "skills",
    REPO / "common" / ".grok" / "skills",
]


def _real_server(max_bytes: int = mcp.DEFAULT_MAX_BYTES) -> mcp.SkillDagServer:
    present = [p for p in REAL_ROOTS if p.is_dir()]
    assert present, f"missing real skill roots under {REPO}"
    return mcp.SkillDagServer(roots=present, max_bytes=max_bytes)


def test_fr6890_folded_yaml_description_is_one_line():
    meta = mcp._parse_frontmatter(
        "---\nname: sample\ndescription: >\n  The single skill for FR jobs.\n"
        "  Second sentence stays.\ndepends_on:\n  - irc\n---\n\nbody\n"
    )
    assert meta["description"] != ">"
    assert "single skill for FR jobs" in meta["description"]
    assert "Second sentence stays" in meta["description"]

    server = _real_server()
    desc = server.nodes["bobiverse-bob-job-fr"]["description"]
    assert desc != ">"
    assert "FR" in desc or "job" in desc.lower()


def test_fr6890_job_line_seed_maps_to_fr_skill():
    server = _real_server()
    out = server.resolve("FR SimonBarnett/bobiverse#6860 index")
    ids = [n["id"] for n in out["matched"]]
    skipped = [s["id"] for s in out.get("skipped") or []]
    assert "bobiverse-bob-job-fr" in ids or "bobiverse-bob-job-fr" in skipped
    assert "bobiverse-bob-job-fr" in ids


def test_fr6890_byte_budget_keeps_seed_skips_later_ancestors():
    server = _real_server()
    out = server.resolve("FR")
    ids = [n["id"] for n in out["matched"]]
    skipped = [s["id"] for s in out.get("skipped") or []]
    assert "bobiverse-bob-job-fr" in ids
    if "harvest" in skipped:
        assert "harvest" not in ids
