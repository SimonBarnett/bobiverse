"""MRB #3484: an FR that names another repo's skill book stays one PR."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"
NEEDLE = (
    "When an FR names a skill book in another repo, land only the assigned "
    "repo in the one PR and file the other book through intake in the same "
    "turn. Do not open a second implement PR from the FR seat."
)


def test_mrb3484_cross_repo_skill_book_is_one_pr():
    skill = SKILL.read_text(encoding="utf-8")
    start = skill.find("## Harvest digest")
    assert start >= 0
    window = skill[start:]
    assert NEEDLE in window
