"""MRB #6575 hostile: FR #6558 BUILD v1 id-less reclaim + explicit id permanence."""
from __future__ import annotations

from pathlib import Path

import bobiverse_build as bb

ROOT = Path(__file__).resolve().parents[2]
BUILD_PY = ROOT / "common" / "scripts" / "bobiverse_build.py"
AGENT_PY = ROOT / "common" / "scripts" / "irc_agent.py"
SKILL = ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-build" / "SKILL.md"
DOCS = ROOT / "docs" / "bobiverse-build.md"


def test_mrb6575_source_explicit_id_never_passes_stale():
    src = BUILD_PY.read_text(encoding="utf-8")
    assert 'explicit_id = bool(str(route.get("id") or "").strip())' in src
    assert "stale = None if explicit_id else stale_claim_s" in src
    assert "dropped as duplicate" in src
    assert "stale_after=" in src
    assert ".reclaim.lock" in src
    assert "Never unlink" in src
    assert "os.replace" in src
    assert "age > ttl" in src
    assert "age2 <= float(stale_after_s)" in src
    assert not BUILD_PY.read_bytes().startswith(b"\xef\xbb\xbf")


def test_mrb6575_agent_wires_recipe_max_and_info_log():
    src = AGENT_PY.read_text(encoding="utf-8")
    needle = "stale_claim_s = bobiverse_build.recipe_max_run_s(recipe)"
    i = src.find(needle)
    assert i >= 0
    window = src[i : i + 800]
    assert "stale_claim_s=stale_claim_s" in window
    assert "log=info" in window
    assert not AGENT_PY.read_bytes().startswith(b"\xef\xbb\xbf")


def test_mrb6575_docs_skill_mention_idless_expiry():
    skill = SKILL.read_text(encoding="utf-8")
    docs = DOCS.read_text(encoding="utf-8")
    blob = skill + "\n" + docs
    assert "6558" in blob
    assert "duplicate" in blob.lower()
    assert not SKILL.read_bytes().startswith(b"\xef\xbb\xbf")
    assert not DOCS.read_bytes().startswith(b"\xef\xbb\xbf")


def test_mrb6575_claim_api_default_permanent(tmp_path: Path):
    """Public claim_build_route_marker without stale_after_s stays permanent."""
    d = tmp_path / "m"
    rid = "h-deadbeefcafebabe"
    assert bb.claim_build_route_marker(d, rid) is True
    aged = d / f"{rid}.claimed"
    aged.write_text("1\n", encoding="ascii")
    assert bb.claim_build_route_marker(d, rid) is False
    assert bb.claim_build_route_marker(d, rid, stale_after_s=10) is True
