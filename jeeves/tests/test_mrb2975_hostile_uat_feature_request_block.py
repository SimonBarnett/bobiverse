"""Hostile MRB #2975: feature-request blocks UAT; harvest: colon receipts do not (FR #2971)."""
from __future__ import annotations

from pathlib import Path

import gitclaim

SKILL = (
    Path(__file__).resolve().parents[2]
    / "bob"
    / ".grok"
    / "skills"
    / "bobiverse-bob-job-uat"
    / "SKILL.md"
)


def test_mrb2975_feature_request_harvest_prose_title_blocks_uat():
    assert (
        gitclaim.issue_blocks_repo_uat(
            title="Harvest re-promotes FAIL-supersede process lessons into harvest (twin MRB loop)",
            labels=("feature-request", "via-intake"),
        )
        is True
    )


def test_mrb2975_colon_harvest_receipt_does_not_block_uat():
    assert (
        gitclaim.issue_blocks_repo_uat(
            title="harvest: skill notes from session",
            labels=("via-intake",),
        )
        is False
    )
    assert (
        gitclaim.issue_blocks_repo_uat(
            title="skill: promote book tips",
            labels=("via-intake", "skill"),
        )
        is False
    )


def test_mrb2975_uat_skill_documents_feature_request_block():
    text = SKILL.read_text(encoding="utf-8")
    assert "FR #2971" in text
    assert "feature-request" in text
    assert "harvest:" in text or "harvest:/" in text
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
