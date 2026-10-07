"""FR #3027: plan-git-from-plan documents many small FRs with Goal/Deliverables/Testable."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
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


def test_plan_git_from_plan_skill_exists():
    assert SKILL.is_file(), SKILL


def test_skill_documents_multi_fr_goal_deliverables_testable_split():
    text = SKILL.read_text(encoding="utf-8-sig")
    assert "Goal" in text and "Deliverables" in text and "Testable" in text
    # Prefer many small feature-request issues before Bob pickup / hand-off
    assert "feature-request" in text
    low = text.lower()
    assert "one pr per issue" in low or "one pr per" in low
    assert "small" in low and ("fr" in low or "feature-request" in low)
    # Must not leave the guidance only as a single umbrella issue
    assert "Goal / Deliverables / Testable" in text or "Goal/Deliverables/Testable" in text
