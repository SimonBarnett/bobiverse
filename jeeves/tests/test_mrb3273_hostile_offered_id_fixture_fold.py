"""MRB #3273: fold FR #3192 offered-id fixture lesson into bobiverse-bob-job-mrb."""
from __future__ import annotations

from repo_layout import ROOT


def test_mrb3273_offered_id_fixture_lesson_in_job_mrb_not_harvest():
    mrb = (ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "offered id" in mrb
    assert "hard-coded" in mrb
    assert "tip #3273" in mrb
    assert "#3205" in mrb or "FR #3205" in mrb
    harvest = (ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    # Tip needle must not land as a harvest lesson bullet (wrong book).
    assert "fixtures must assert the offered id not hard-coded FR#1" not in harvest
