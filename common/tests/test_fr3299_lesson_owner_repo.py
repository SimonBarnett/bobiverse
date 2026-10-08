"""FR #3299: lesson_owner_repo helper + LESSON_PR_MRB_INSTRUCTION owning-repo wording."""
from __future__ import annotations

from pathlib import Path

import gitclaim
import intake
import re


def test_fr3299_lesson_pr_mrb_instruction_mentions_owning_repo():
    text = intake.LESSON_PR_MRB_INSTRUCTION
    assert "light triage" in text.lower() or "useful" in text.lower()
    assert "re-file" in text.lower() or "MOVED" in text
    assert "OPEN" in text


def test_fr3299_lesson_owner_repo_fixtures():
    """Replay real tip cues from FR #3299 acceptance."""
    # #3046 / #3047 Plan-seat xlsx -> skills-visionary
    own = intake.lesson_owner_repo(
        title="harvest: Plan-seat xlsx export playbook",
        body="Lessons:\n- Plan xlsx helpers belong with harvest-skills-visionary\n",
    )
    assert own.repo == "SimonBarnett/skills-visionary"
    assert own.missing is False

    # #3097 / #3098 / #3099 iphone-text-bridge (planned product) -> hold-open
    own2 = intake.lesson_owner_repo(
        title="harvest: iphone-text-bridge Shortcuts all-SMS recipe",
        body="Architecture for SimonBarnett/iphone-text-bridge SMS bridge.\n",
    )
    assert own2.repo == "SimonBarnett/iphone-text-bridge"
    assert own2.missing is True

    own2b = intake.lesson_owner_repo(
        title="harvest: Shortcuts all-SMS recipe",
        body="iPhone text bridge recipe for all SMS.\n",
    )
    assert own2b.repo == "SimonBarnett/iphone-text-bridge"
    assert own2b.missing is True

    # a-search FR lesson
    own3 = intake.lesson_owner_repo(
        title="harvest: a-search DefaultQueryParts CDK synth",
        body="Lessons:\n- Awin local DefaultQueryParts must survive cdk synth\n",
    )
    assert own3.repo == "SimonBarnett/a-search"
    assert own3.missing is False

    # bob-worker _release_gen lesson stays bobiverse
    own4 = intake.lesson_owner_repo(
        title="harvest: bob-worker done-miss _release_gen sync",
        body="Lessons:\n- _release_gen must bump when DONE is drained\n",
    )
    assert own4.repo == "SimonBarnett/bobiverse"
    assert own4.missing is False

    # Unknown / empty -> None
    own5 = intake.lesson_owner_repo(title="harvest: misc tip", body="Lessons:\n- something vague\n")
    assert own5.repo is None
    assert own5.missing is False


def test_fr3299_lesson_owner_explicit_repo_and_trutex():
    own = intake.lesson_owner_repo(
        title="harvest: Trutex knowledge routing",
        body="belongs in SimonBarnett/trutex knowledge pack\n",
    )
    assert own.repo == "SimonBarnett/trutex"
    assert own.missing is False


def test_fr3299_draft_skill_body_prepending_mrb_instruction(tmp_path: Path):
    """kind=skill without Lessons: still carries LESSON_PR_MRB_INSTRUCTION on the draft PR."""
    filer = intake.FakeGitHubFiler()
    err, norm = intake.validate_payload(
        {
            "kind": "skill",
            "repo": "SimonBarnett/bobiverse",
            "title": "skill: promote ARP VERSION truth tip",
            "body": "Promote the ARP DisplayVersion playbook into bobiverse-fleet-ops.\n",
            "source": {"skill_book": "bobiverse-fleet-ops", "agent": "worker"},
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_fr3299_skill")
    assert rec["state"] == "filed"
    assert filer.prs, "expected a draft skill PR"
    pr = filer.prs[-1]
    body = pr.get("body") or ""
    assert intake.LESSON_PR_MRB_INSTRUCTION in body
    assert "light triage" in body.lower() or "useful" in body.lower()


def test_fr3299_mrb_moved_verdict_title_is_skip_fr():
    """MOVED boards are recorded as done (mrb_verdict_title), not re-offered as FR."""
    assert (
        gitclaim.issue_skip_fr_reason(
            title="MRB MOVED - SimonBarnett/skills-visionary#26",
            labels=(),
        )
        == "mrb_verdict_title"
    )
    assert (
        gitclaim.issue_skip_fr_reason(
            title="MRB MOVED: SimonBarnett/a-search#42",
            labels=(),
        )
        == "mrb_verdict_title"
    )
    assert re.search(gitclaim.MRB_VERDICT_TITLE_RE, "MRB MOVED - owner/repo#1")
    assert re.search(gitclaim.MRB_VERDICT_TITLE_RE, "MRB MOVED: owner/repo#1")
    assert not re.search(gitclaim.MRB_VERDICT_TITLE_RE, "MRB MOVED owner/repo#1")  # needs separator
    # Still does not block repo UAT.
    assert (
        gitclaim.issue_blocks_repo_uat(
            title="MRB MOVED - SimonBarnett/skills-visionary#26",
            labels=(),
        )
        is False
    )
