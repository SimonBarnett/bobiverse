"""FR #6941: change-review-findings skill is indexed, unique, and resolve-safe."""
from __future__ import annotations

from pathlib import Path

import skill_dag_index as idx
import skill_dag_mcp as mcp

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "common" / ".grok" / "skills" / "change-review-findings" / "SKILL.md"
REAL_ROOTS = [
    REPO / "bob" / ".grok" / "skills",
    REPO / "common" / ".grok" / "skills",
]


def _roots() -> list[Path]:
    present = [p for p in REAL_ROOTS if p.is_dir()]
    assert present
    return present


def test_fr6941_file_credits_ponytail_and_does_not_replace_mrb():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "Dietrich Gebert" in text
    assert "MIT" in text
    assert "ponytail" in text.lower()
    assert "does not replace" in text.lower()
    assert "bobiverse-bob-job-mrb" in text


def test_fr6941_index_unique_empty_deps_no_cycle():
    nodes, collisions = idx.scan_skills_with_collisions(_roots())
    hits = [n for n in nodes if n["id"] == "change-review-findings"]
    assert len(hits) == 1
    node = hits[0]
    assert Path(node["path"]).resolve() == SKILL.resolve()
    assert list(node["depends_on"] or []) == []
    assert not any(c.get("id") == "change-review-findings" for c in collisions)
    ids = [n["id"] for n in nodes]
    assert ids.count("change-review-findings") == 1
    cycle = idx.find_cycle(nodes)
    assert cycle is None
    mrb = next(n for n in nodes if n["id"] == "bobiverse-bob-job-mrb")
    assert "change-review-findings" not in [str(d) for d in (mrb.get("depends_on") or [])]


def test_fr6941_resolve_exact_id_under_default_cap():
    server = mcp.SkillDagServer(roots=_roots())
    assert "change-review-findings" in server.nodes
    out = server.resolve("change-review-findings")
    ids = [n["id"] for n in out["matched"]]
    skipped = [s["id"] for s in out.get("skipped") or []]
    assert "change-review-findings" in ids
    assert "change-review-findings" not in skipped
    used = 64 + sum(n["bytes"] + len(str(n).encode("utf-8")) for n in out["matched"])
    assert used <= mcp.DEFAULT_MAX_BYTES
    got = server.get_skill(str(SKILL))
    assert got.get("ok") is True
    assert "Must fix" in (got.get("body") or "")
