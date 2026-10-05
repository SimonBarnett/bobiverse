from __future__ import annotations

from pathlib import Path

import pytest

import intake
from repo_layout import ROOT


class DraftPrDown:
    def create_draft_pr(self, *args, **kwargs):
        raise RuntimeError("draft PR unavailable")

    def create_issue(self, *args, **kwargs):
        raise AssertionError("harvest receipt must not fall back to an issue")


def test_worker_receipt_issue_is_rejected():
    err, _ = intake.validate_payload(
        {
            "kind": "issue",
            "repo": "SimonBarnett/bobiverse",
            "title": "harvest: GIVEUP MRB #2241 self-MRB",
            "body": "Session summary:\nGIVEUP MRB #2241 self-MRB",
        }
    )
    assert err == "worker_receipt_not_issue"


def test_real_harvest_kind_is_not_treated_as_issue():
    err, _ = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": "SimonBarnett/bobiverse",
            "title": "harvest: durable skill proposal",
            "body": "Session summary:\nA real playbook lesson",
        }
    )
    assert err is None


def test_harvest_pr_failure_queues_without_issue(tmp_path: Path):
    # FR #2595: DONE/GIVEUP harvest receipts are record-only (no draft PR attempt).
    # Queued-on-draft-failure still applies to non-receipt harvest playbooks.
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": "SimonBarnett/bobiverse",
            "title": "harvest: GIVEUP MRB #2241 self-MRB",
            "body": "Session summary:\nGIVEUP MRB #2241 self-MRB",
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, DraftPrDown(), intake_id="in_receipt2181")
    assert rec["state"] == "receipt_recorded"
    assert not list((tmp_path / "intake").glob("**/*issue*"))
    assert not (tmp_path / "intake" / "outbox" / "in_receipt2181.json").is_file()


def test_harvest_playbook_draft_failure_still_queues_without_issue(tmp_path: Path):
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": "SimonBarnett/bobiverse",
            "title": "harvest: durable tip utf8 write playbook",
            "body": "Session summary:\nWrite tip scripts with python/git bytes.",
        }
    )
    assert err is None
    with pytest.raises(intake.GitHubDown):
        intake.file_submission(tmp_path, norm, DraftPrDown(), intake_id="in_playbook2181")
    assert not list((tmp_path / "intake").glob("**/*issue*"))
    assert (tmp_path / "intake" / "outbox" / "in_playbook2181.json").is_file()


def test_worker_prompt_contains_no_receipt_issue_rule():
    text = (ROOT / "bob/scripts/bob_worker.py").read_text(encoding="utf-8-sig")
    assert "Never file the worker status receipt itself" in text
    assert "SKIP/self-MRB" in text
