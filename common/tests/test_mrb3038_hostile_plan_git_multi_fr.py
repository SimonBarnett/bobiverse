"""MRB #3038 hostile pins: FR #3027 multi-FR Goal/Deliverables/Testable in plan-git-from-plan."""
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


def test_mrb3038_skill_has_split_backlog_step():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "Split the backlog into many small FRs" in text
    assert "Goal / Deliverables / Testable" in text
    assert "one PR per issue" in text or "one PR per" in text
    assert "umbrella issue" in text.lower() or "Do **not** park the whole product as one" in text


def test_mrb3038_keeps_intake_allow_and_fr_path():
    text = SKILL.read_text(encoding="utf-8")
    # FR #3135: SimonBarnett/* owner gate (no per-repo DEFAULT_ALLOW_REPOS churn).
    assert "SimonBarnett/" in text
    assert "3135" in text or "DEFAULT_ALLOW_REPOS" in text or "intake" in text.lower()
    assert "feature-request" in text
    # FR path also mentions Goal/Deliverables/Testable
    assert text.count("Goal / Deliverables / Testable") >= 1
