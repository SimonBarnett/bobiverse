"""MRB #6943 hostile pin: change-review-findings stays on main with empty deps."""
from __future__ import annotations

from pathlib import Path

import skill_dag_index as idx
import skill_dag_mcp as mcp

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "common" / ".grok" / "skills" / "change-review-findings" / "SKILL.md"
MRB = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"


def test_mrb6943_skill_credits_and_does_not_replace_mrb():
    text = SKILL.read_text(encoding="utf-8")
    assert "Dietrich Gebert" in text
    assert "MIT" in text
    assert "does not replace" in text.lower()
    assert "bobiverse-bob-job-mrb" in text


def test_mrb6943_empty_depends_on_and_not_hard_dep_of_mrb():
    roots = [p for p in (REPO / "bob" / ".grok" / "skills", REPO / "common" / ".grok" / "skills") if p.is_dir()]
    nodes, _ = idx.scan_skills_with_collisions(roots)
    node = next(n for n in nodes if n["id"] == "change-review-findings")
    assert list(node["depends_on"] or []) == []
    mrb = next(n for n in nodes if n["id"] == "bobiverse-bob-job-mrb")
    assert "change-review-findings" not in [str(d) for d in (mrb.get("depends_on") or [])]
    mrb_text = MRB.read_text(encoding="utf-8")
    # frontmatter depends_on must not list the new skill
    fm = mcp._parse_frontmatter(mrb_text)
    assert "change-review-findings" not in [str(d) for d in (fm.get("depends_on") or [])]


def test_mrb6943_resolve_exact_id():
    roots = [p for p in (REPO / "bob" / ".grok" / "skills", REPO / "common" / ".grok" / "skills") if p.is_dir()]
    server = mcp.SkillDagServer(roots=roots)
    out = server.resolve("change-review-findings")
    assert "change-review-findings" in [n["id"] for n in out["matched"]]
