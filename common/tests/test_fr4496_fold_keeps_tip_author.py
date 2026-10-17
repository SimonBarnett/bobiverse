"""FR #4496: a fold on a product tip keeps the tip git author."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = (
    ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"
)
NEEDLE = (
    "A fold or tip-fix commit on an open product tip keeps the existing tip "
    "author name and email for that commit only via `git -c user.name` and "
    "`git -c user.email` (copy `git log -1 --format`). Never commit as the "
    "reviewing seat nick. Do not change git config."
)


def test_fr4496_self_mrb_keeps_tip_author_on_fold():
    skill = SKILL.read_text(encoding="utf-8")
    start = skill.find("## Self-MRB (harvest #1603 / MRB #1578)")
    end = skill.find("## Harvest-lesson intake PRs", start)
    assert start >= 0 and end > start
    window = skill[start:end]
    assert NEEDLE in window
    assert "git config user.name" not in window
