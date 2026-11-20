"""Hostile MRB #2738: harvest lessons archive keeps Clear reclaim lesson (FR #2727)."""
from __future__ import annotations

from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / ".grok" / "skills" / "harvest" / "SKILL.md"
LESSONS = Path(__file__).resolve().parents[1] / ".grok" / "skills" / "harvest" / "lessons.md"


def test_mrb2738_harvest_skill_has_clear_reclaim_lesson():
    skill = SKILL.read_text(encoding="utf-8")
    archive = LESSONS.read_text(encoding="utf-8")
    assert "## Harvested lessons (intake)" in skill
    assert "lessons.md" in skill
    # FR #8310: Clear reclaim tip lives in lessons.md archive.
    assert "Clear-BobiverseJobWorktrees" in archive
    assert "hand-delete" in archive or "Remove-Item" in archive or "wt-bob-main" in archive
    assert ".bobiverse-seat" in archive
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
