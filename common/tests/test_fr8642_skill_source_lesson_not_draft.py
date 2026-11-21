"""FR #8642: empty-file harvest/skill opens an offerable skill-source tip.

docs/intake-harvest-only drafts never enter MRB (FR #6356). A Plan body with
no Lessons: list must still land under docs/skill-sources/ as a non-draft
lesson(...). Session-summary receipts stay unfiled.
"""
from __future__ import annotations

from pathlib import Path

import gitclaim
import intake

REPO = "SimonBarnett/skills-visionary"


def test_fr8642_empty_harvest_opens_skill_source_not_draft(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": REPO,
            "title": "Plan seat: file-all opens each backlog draft via intake",
            "body": (
                "what: Operator file-all opens each backlog draft with the intake script.\n"
                "where: skills-visionary plan seat.\n"
            ),
            "source": {"skill_book": "harvest-skills-visionary", "agent": "plan-file-all"},
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_plan8642")
    assert rec["state"] == "filed"
    assert filer.prs
    pr = filer.prs[-1]
    assert pr.get("draft") is False
    assert str(pr["title"]).startswith("lesson(")
    assert "harvest-lesson" in pr["labels"]
    paths = [f.get("path") for f in pr.get("files") or []]
    assert paths
    assert not gitclaim.is_intake_harvest_only_paths(paths)
    assert any(str(p).startswith("docs/skill-sources/") for p in paths)
    assert "Lessons:" in (pr.get("body") or "")
    assert gitclaim.is_offerable_intake_skill_lesson_pr(
        title=pr["title"],
        body=pr["body"],
        labels=pr["labels"],
        files=paths,
    )


def test_fr8642_session_summary_receipt_stays_unfiled(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": REPO,
            "title": "harvest: seat finished a review",
            "body": "Session summary:\nReviewed the skill book and left the tip.\n",
            "source": {"agent": "Invoke-BobiverseHarvest"},
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_sum8642")
    assert rec["state"] == "receipt_recorded"
    assert filer.prs == []


def test_fr8642_intake_harvest_only_still_receipt():
    paths = ["docs/intake-harvest/intake-in_x.md"]
    assert gitclaim.is_intake_harvest_only_paths(paths)
    assert gitclaim.is_intake_harvest_receipt_pr(
        title="lesson(harvest): already drafted",
        body="Lessons:\n- a real line\n",
        labels=["via-intake", "harvest-lesson"],
        files=paths,
    )
