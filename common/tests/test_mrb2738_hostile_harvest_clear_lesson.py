"""Hostile MRB #2738: harvest SKILL keeps Clear reclaim lesson (FR #2727 playbook)."""
from __future__ import annotations

from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / ".grok" / "skills" / "harvest" / "SKILL.md"


def test_mrb2738_harvest_skill_has_clear_reclaim_lesson():
    text = SKILL.read_text(encoding="utf-8")
    assert "## Harvested lessons (intake)" in text
    assert "Clear-BobiverseJobWorktrees" in text
    assert "hand-delete" in text or "Remove-Item" in text or "wt-bob-main" in text
    assert ".bobiverse-seat" in text
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
