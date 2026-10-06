"""MRB #2651 hostile: edited/synchronize must not enqueue harvest-receipt MRB."""
from __future__ import annotations

import json
from pathlib import Path

import gitclaim
import intake


REPO = "SimonBarnett/bobiverse"


def _pr_payload(*, number: int, title: str, body: str, action: str, draft: bool = False, labels=None):
    labs = [{"name": n} for n in (labels or [])]
    return {
        "action": action,
        "repository": {"full_name": REPO},
        "pull_request": {
            "number": number,
            "title": title,
            "body": body,
            "draft": draft,
            "html_url": f"https://github.com/{REPO}/pull/{number}",
            "labels": labs,
            "merged": False,
        },
    }


def test_mrb2651_edited_harvest_receipt_produces_no_claim():
    claim = gitclaim.claim_from_payload(
        "pull_request",
        _pr_payload(
            number=2647,
            title="harvest: MRB #2642 PASS: merged",
            body="Session summary:\nPASS\n_via-intake Invoke-BobiverseHarvest_",
            action="edited",
            draft=False,
            labels=["via-intake", "skill"],
        ),
    )
    assert claim is None


def test_mrb2651_synchronize_harvest_receipt_produces_no_claim():
    claim = gitclaim.claim_from_payload(
        "pull_request",
        _pr_payload(
            number=2647,
            title="harvest: twin of #2647",
            body="Session summary:\ntwin\n_via-intake Invoke-BobiverseHarvest_",
            action="synchronize",
            labels=["via-intake", "skill"],
        ),
    )
    assert claim is None


def test_mrb2651_edited_draft_produces_no_claim():
    claim = gitclaim.claim_from_payload(
        "pull_request",
        _pr_payload(
            number=99,
            title="fix(bob): WIP",
            body="Closes #98",
            action="edited",
            draft=True,
        ),
    )
    assert claim is None


def test_mrb2651_edited_real_pr_still_claims():
    claim = gitclaim.claim_from_payload(
        "pull_request",
        _pr_payload(
            number=2651,
            title="fix(jeeves): skip draft harvest receipts",
            body="Closes SimonBarnett/bobiverse#2650",
            action="edited",
            draft=False,
        ),
    )
    assert claim is not None
    assert claim.task == "MRB"
    assert claim.action == "edited"


def test_mrb2651_pass_marker_in_intake_source():
    src = Path(intake.__file__).read_text(encoding="utf-8")
    assert "PASS" in src
    assert "FAIL" in src
    assert "_HARVEST_KIND_RECEIPT_MARKER" in src


def test_mrb2651_edited_receipt_apply_adds_nothing(tmp_path: Path):
    home = tmp_path / "chair"
    home.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    claim = gitclaim.claim_from_payload(
        "pull_request",
        _pr_payload(
            number=2647,
            title="harvest: MRB #2642 PASS: merged",
            body="Session summary:\nPASS\n_via-intake Invoke-BobiverseHarvest_",
            action="edited",
            labels=["via-intake", "skill"],
        ),
    )
    assert claim is None
    rows = gitclaim.load_unaccepted(home)
    assert rows == []
