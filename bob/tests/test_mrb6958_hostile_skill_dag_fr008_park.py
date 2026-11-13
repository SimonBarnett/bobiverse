"""Hostile MRB #6958: FR-008 docs park; #6901 stays open; resolve still first-token seeds."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

INDEX = ROOT / "bob/docs/feature-request-worker-skill-dag-mcp-2026-11-12.md"
MIRROR = ROOT / "bob/docs/fr/worker-skill-dag/FR-008-resolve-scores-descriptions.md"
TSV = ROOT / "bob/docs/fr/worker-skill-dag/SMALL-FRS.tsv"
MCP = ROOT / "bob/scripts/skill_dag_mcp.py"
MOJIBAKE = "\u00e2" + "\u20ac"


def test_mrb6958_tsv_maps_fr008_to_6901():
    rows = {}
    for line in TSV.read_text(encoding="utf-8").splitlines()[1:]:
        if not line.strip():
            continue
        parts = line.split("\t")
        assert len(parts) >= 2, line
        rows[parts[0]] = parts[1]
    assert rows["FR-008"] == "6901"


def test_mrb6958_mirror_refs_6901_stays_open_no_closes():
    raw = MIRROR.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert MOJIBAKE not in text
    assert "#6901" in text or "6901" in text
    assert "Stays open" in text
    assert "Docs park" in text
    for line in text.splitlines():
        assert not line.strip().startswith("Closes ")
    assert "JOB_SEEDS" in text
    assert "_seed_id" in text
    assert "does not use the description to choose the seed" in text
    assert "6918" in text and "6919" in text
    assert "Not reopened" in INDEX.read_text(encoding="utf-8") or "Not reopened" in text


def test_mrb6958_index_follow_up_not_closes():
    text = INDEX.read_text(encoding="utf-8")
    assert "## Follow-up" in text
    assert "6901" in text
    assert "FR-008" in text
    assert "Stays open" in text
    assert "6918" in text and "6919" in text
    for line in text.splitlines():
        assert not line.strip().startswith("Closes ")


def test_mrb6958_live_resolve_still_first_token_not_description_score():
    src = MCP.read_text(encoding="utf-8")
    assert "JOB_SEEDS" in src
    assert "def _seed_id" in src
    assert "first in JOB_SEEDS" in src
    # JOB_SEEDS first-token still wins; docstring may cite FR #6901 description scoring.
    assert "def resolve" in src
    seed = src[src.index("def _seed_id") : src.index("def resolve")]
    jobs = seed.index("JOB_SEEDS")
    desc = seed.find("score_description")
    assert jobs >= 0
    if desc >= 0:
        assert jobs < desc, "JOB_SEEDS first-token must run before description score"
