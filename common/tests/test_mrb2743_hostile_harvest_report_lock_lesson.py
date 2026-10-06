"""Hostile MRB #2743: harvest SKILL keeps report/pr_exists lock lesson (FR #2729)."""
from __future__ import annotations

from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / ".grok" / "skills" / "harvest" / "SKILL.md"


def test_mrb2743_harvest_skill_has_report_pr_exists_lock_lesson():
    text = SKILL.read_text(encoding="utf-8")
    assert "## Harvested lessons (intake)" in text
    assert "pr_exists" in text
    assert "/bob/v1/report" in text or "report" in text
    assert "queue lock" in text or "gitclaim" in text
    assert "single-flight" in text or "lock_timeout" in text
    # Keep-both with prior Clear reclaim lesson
    assert "Clear-BobiverseJobWorktrees" in text
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
