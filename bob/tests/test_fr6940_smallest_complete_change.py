"""FR #6940: harvest skill smallest-complete-change (ponytail MIT)."""
from __future__ import annotations

from pathlib import Path

import skill_dag_index as idx
import skill_dag_mcp as mcp

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "common" / ".grok" / "skills" / "smallest-complete-change" / "SKILL.md"
ROOTS = [
    REPO / "bob" / ".grok" / "skills",
    REPO / "common" / ".grok" / "skills",
]


def test_fr6940_skill_file_credits_ponytail_mit():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "Ponytail" in text or "ponytail" in text.lower()
    assert "MIT" in text
    assert "Dietrich Gebert" in text
    assert "2026" in text
    assert "https://github.com/DietrichGebert/ponytail" in text
    assert len(raw) < 8000


def test_fr6940_frontmatter_unique_empty_deps_indexed():
    present = [p for p in ROOTS if p.is_dir()]
    nodes, collisions = idx.scan_skills_with_collisions(present)
    ids = [n["id"] for n in nodes]
    assert ids.count("smallest-complete-change") == 1
    node = next(n for n in nodes if n["id"] == "smallest-complete-change")
    assert Path(node["path"]).resolve() == SKILL.resolve()
    assert list(node["depends_on"] or []) == []
    collide_ids = {c["id"] for c in collisions}
    assert "smallest-complete-change" not in collide_ids
    cycle = idx.find_cycle(nodes)
    assert cycle is None


def test_fr6940_resolve_exact_id_under_budget():
    present = [p for p in ROOTS if p.is_dir()]
    server = mcp.SkillDagServer(roots=present)
    out = server.resolve("smallest-complete-change")
    ids = [n["id"] for n in out["matched"]]
    skipped = [s["id"] for s in out.get("skipped") or []]
    assert "smallest-complete-change" in ids
    assert "smallest-complete-change" not in skipped
    node = next(n for n in out["matched"] if n["id"] == "smallest-complete-change")
    got = server.get_skill(node["path"])
    assert got.get("ok") is True
    used = sum(n["bytes"] for n in out["matched"])
    assert used < mcp.DEFAULT_MAX_BYTES


def test_fr6940_job_fr_does_not_hard_depend():
    fr = (
        REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"
    ).read_text(encoding="utf-8")
    head = fr.split("---", 2)[1] if fr.startswith("---") else fr[:400]
    assert "smallest-complete-change" not in head
