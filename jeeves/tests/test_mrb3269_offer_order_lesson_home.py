"""MRB #3269: offer-order / deferred-precompute lesson lives in bobiverse-bob-job-mrb."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT


def test_mrb3269_lesson_in_job_mrb_not_harvest():
    mrb = (ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "owner/repo" in mrb and "mrb_row_offerable" in mrb
    assert "ACCEPTABLE drift" in mrb and "precompute" in mrb.lower()
    harvest = (ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    # Tip must not land the product/MRB needle as a harvest bullet (wrong book).
    assert "mrb_row_offerable skips" not in harvest
