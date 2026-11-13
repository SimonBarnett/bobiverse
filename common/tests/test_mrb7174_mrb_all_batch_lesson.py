"""MRB #7174 MOVED: MRB-ALL batch lesson lives in bobiverse-bob-job-mrb, not harvest."""
from __future__ import annotations

from pathlib import Path

from repo_layout import REPO

SKILL = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"
HARVEST = REPO / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"


def test_mrb7174_mrb_all_batch_lesson_contiguous():
    text = SKILL.read_text(encoding="utf-8")
    start = text.index("MRB-ALL batch (class of redqueen MRB-ALL 2026-11-13):")
    window = text[start : start + 320]
    assert "re-list open PRs every batch" in window
    assert "prior self-MRB tips may already be gone" in window
    assert "merge every remaining non-self non-draft tip" in window
    assert "Do not park this playbook under `harvest/SKILL.md`" in window


def test_mrb7174_not_parked_under_harvest_main_copy():
    # Durable home is job-mrb; harvest must not gain a second copy of this bullet.
    h = HARVEST.read_text(encoding="utf-8")
    assert "MRB-ALL: re-list open PRs every batch" not in h
