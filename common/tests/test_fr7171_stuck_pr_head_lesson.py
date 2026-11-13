"""FR #7171: pin stuck refs/pull head lesson in bobiverse-bob-job-mrb."""
from __future__ import annotations

from pathlib import Path

from repo_layout import REPO

SKILL = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"


def test_fr7171_stuck_pr_head_lesson_contiguous():
    text = SKILL.read_text(encoding="utf-8")
    start = text.index("Stuck PR head after stacked tip fix (FR #7171")
    window = text[start : start + 360]
    assert "`refs/pull/N/head`" in window
    assert "mainland fix PR targeting `main`" in window
    assert "Do not park this playbook under `harvest/SKILL.md`" in window
    assert "FIX with stacked fix PR already open (MRB #6336" in text
