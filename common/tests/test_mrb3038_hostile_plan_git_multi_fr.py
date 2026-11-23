"""MRB #3038 hostile pins: FR #3027 multi-FR guidance (FR #8833 retarget).

plan-git-from-plan lives in skills-visionary; bobiverse pointer README only.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "bob" / "agents" / "plan" / "README.md"
SKILL = (
    ROOT
    / "bob"
    / "agents"
    / "plan"
    / ".grok"
    / "skills"
    / "plan-git-from-plan"
    / "SKILL.md"
)


def test_mrb3038_plan_git_skill_removed():
    assert not SKILL.exists()
    assert README.is_file()
    assert "skills-visionary" in README.read_text(encoding="utf-8")
