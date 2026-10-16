"""MRB #4498: an FR assign of an intake this seat filed is not self-MRB."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = (
    ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"
)
NEEDLE = (
    "When this seat is later assigned the intake it just filed, implement "
    "that issue. Self-MRB applies only when this seat is assigned the MRB "
    "of a PR it opened or pushed."
)


def test_mrb4498_fr_assign_is_not_self_mrb():
    skill = SKILL.read_text(encoding="utf-8")
    start = skill.find("## Self-MRB (harvest #1603 / MRB #1578)")
    end = skill.find("## Harvest-lesson intake PRs", start)
    assert start >= 0 and end > start
    window = skill[start:end]
    assert NEEDLE in window
    assert "FR assign is not self-MRB" in window
