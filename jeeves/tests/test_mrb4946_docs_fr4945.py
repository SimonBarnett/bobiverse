"""MRB #4946 docs pin: FR #4945 RepoRoot product install is documented."""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FLEET = REPO / "common" / ".grok" / "skills" / "bobiverse-fleet-ops" / "SKILL.md"
FR_SKILL = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"


def test_mrb4946_fleet_ops_mentions_fr4945_repo_root():
    t = FLEET.read_text(encoding="utf-8")
    assert "FR #4945" in t
    assert "a-search" in t
    assert "RepoRoot" in t


def test_mrb4946_job_fr_mentions_product_reporoot():
    t = FR_SKILL.read_text(encoding="utf-8")
    assert "FR #4945" in t
    assert "a-search" in t
    assert "RepoRoot" in t
