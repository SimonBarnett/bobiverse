"""FR #3027: multi-FR Goal/Deliverables/Testable lived in plan-git-from-plan.

FR #8833: that skill moved to skills-visionary; bobiverse keeps a pointer README.
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


def test_plan_git_from_plan_skill_removed_pointer_readme():
    assert not SKILL.exists()
    assert README.is_file()
    text = README.read_text(encoding="utf-8")
    assert "skills-visionary" in text
