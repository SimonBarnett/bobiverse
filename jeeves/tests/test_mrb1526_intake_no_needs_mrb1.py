"""MRB #1526 nits: intake must not stamp needs-mrb1 (FR #1523 / operator 2026-10-04)."""
from __future__ import annotations

import intake


def test_labels_for_fr_and_issue_omit_needs_mrb1():
    for kind in ("fr", "issue"):
        labs = intake._labels_for(
            {"kind": kind, "title": "intake: stop auto needs-mrb1", "body": "x"},
            quarantine=False,
        )
        assert "needs-mrb1" not in labs
        assert "via-intake" in labs
        if kind == "fr":
            assert "feature-request" in labs


def test_labels_for_skill_harvest_omit_needs_mrb1():
    for kind in ("skill", "harvest"):
        labs = intake._labels_for(
            {"kind": kind, "title": "harvest: seats idle", "body": "x"},
            quarantine=False,
        )
        assert "needs-mrb1" not in labs
        assert "skill" in labs


def test_labels_for_quarantine_still_marks_untriaged():
    labs = intake._labels_for(
        {"kind": "fr", "title": "FR: x", "body": ""},
        quarantine=True,
    )
    assert "via-intake-untriaged" in labs
    assert "needs-mrb1" not in labs
