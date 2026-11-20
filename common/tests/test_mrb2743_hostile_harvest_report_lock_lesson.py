"""Hostile MRB #2743: harvest lessons archive keeps report/pr_exists lock lesson (FR #2729)."""
from __future__ import annotations

from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / ".grok" / "skills" / "harvest" / "SKILL.md"
LESSONS = Path(__file__).resolve().parents[1] / ".grok" / "skills" / "harvest" / "lessons.md"


def test_mrb2743_harvest_skill_has_report_pr_exists_lock_lesson():
    skill = SKILL.read_text(encoding="utf-8")
    archive = LESSONS.read_text(encoding="utf-8")
    assert "## Harvested lessons (intake)" in skill
    assert "lessons.md" in skill
    # FR #8310: report/pr_exists tip lives in lessons.md archive.
    assert "pr_exists" in archive
    assert "/bob/v1/report" in archive or "report" in archive
    assert "queue lock" in archive or "gitclaim" in archive
    assert "single-flight" in archive or "lock_timeout" in archive
    # Keep-both with prior Clear reclaim lesson (also archived)
    assert "Clear-BobiverseJobWorktrees" in archive
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
