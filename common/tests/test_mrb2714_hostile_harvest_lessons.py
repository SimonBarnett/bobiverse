"""MRB #2714 hostile: FR #2705 harvest-lesson skill-book edges."""
from __future__ import annotations

from pathlib import Path

import gitclaim
import intake


REPO = "SimonBarnett/bobiverse"
HARVEST_SKILL = "common/.grok/skills/harvest/SKILL.md"


def test_mrb2714_receipt_title_with_harvest_lesson_label_is_offerable():
    assert (
        gitclaim.is_intake_harvest_receipt_pr(
            title="harvest: MRB #1 PASS: merged",
            body="Session summary:\nDONE\n_via-intake Invoke-BobiverseHarvest_",
            labels=["via-intake", "skill", "harvest-lesson"],
        )
        is False
    )


def test_mrb2714_lesson_title_without_label_is_offerable():
    assert (
        gitclaim.is_intake_harvest_receipt_pr(
            title="lesson(harvest): EncodedCommand must silence ProgressPreference",
            body="verify that the lesson is generalised\nSession summary:",
            labels=["via-intake"],
        )
        is False
    )


def test_mrb2714_draft_harvest_receipt_still_blocked():
    assert (
        gitclaim.is_intake_harvest_receipt_pr(
            title="harvest: session tip",
            body="Session summary:\nnothing\n_via-intake Invoke-BobiverseHarvest_",
            labels=["via-intake", "skill"],
        )
        is True
    )


def test_mrb2714_apply_lessons_inserts_before_later_heading():
    base = "# Book\n\n## Harvested lessons (intake)\n\n- old\n\n## Other\n\nTail.\n"
    out = intake.apply_lessons_to_skill_md(base, ["new lesson"])
    assert out.count("## Harvested lessons (intake)") == 1
    assert out.index("- new lesson") < out.index("## Other")
    assert "- old" in out


def test_mrb2714_extract_dedupes_and_keeps_order():
    body = "Lessons:\n- Alpha tip\n- Beta tip\n- Alpha tip\n- (no new playbook line)\n"
    assert intake.extract_harvest_lessons(body) == ["Alpha tip", "Beta tip"]


def test_mrb2714_path_skill_book_resolution():
    book, path = intake.resolve_skill_book(
        skill_book="bob/.grok/skills/bobiverse-bob-worker/SKILL.md",
        title="x",
        body="y",
    )
    assert book == "bobiverse-bob-worker"
    assert path.endswith("bobiverse-bob-worker/SKILL.md")


def test_mrb2714_invoke_harvest_book_param_in_ps1():
    ps1 = Path(__file__).resolve().parents[1] / "scripts" / "Invoke-BobiverseHarvest.ps1"
    text = ps1.read_text(encoding="utf-8")
    assert "[string]$Book" in text or "$Book" in text
    assert "skill_book" in text


def test_mrb2714_webhook_offers_lesson_pr_even_if_title_has_pass():
    """harvest-lesson PRs stay MRB-offerable even when the tip text mentions PASS."""
    claim = gitclaim.claim_from_payload(
        "pull_request",
        {
            "action": "opened",
            "repository": {"full_name": REPO},
            "pull_request": {
                "number": 2714,
                "title": "lesson(harvest): PASS board playbook tip",
                "body": "MRB: verify that the lesson is generalised and placed in the right SKILL.md\n",
                "draft": False,
                "html_url": f"https://github.com/{REPO}/pull/2714",
                "labels": [{"name": "via-intake"}, {"name": "harvest-lesson"}],
                "merged": False,
            },
        },
    )
    assert claim is not None
    assert claim.task == "MRB"
    assert claim.id == "#2714"


def test_mrb2714_job_mrb_skill_documents_harvest_lesson_review():
    skill = (
        Path(__file__).resolve().parents[2]
        / "bob"
        / ".grok"
        / "skills"
        / "bobiverse-bob-job-mrb"
        / "SKILL.md"
    )
    text = skill.read_text(encoding="utf-8")
    assert "## Harvest-lesson intake PRs (FR #2705)" in text
    assert "harvest-lesson" in text
    assert "generalised" in text or "generalized" in text
