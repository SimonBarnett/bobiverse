"""MRB #2269 hostile: receipt guard keeps FR #1812 linked_existing_pr + no BOM."""
from __future__ import annotations

from pathlib import Path

import pytest

import intake
from repo_layout import ROOT


def test_mrb2269_intake_and_tests_no_bom():
    for rel in (
        "common/scripts/intake.py",
        "common/tests/test_fr2181_worker_receipts.py",
        "common/.grok/skills/harvest/SKILL.md",
        "bob/.grok/skills/bobiverse-bob-job-irc/SKILL.md",
    ):
        p = ROOT / rel
        assert p.is_file(), p
        assert not p.read_bytes().startswith(b"\xef\xbb\xbf"), rel


def test_mrb2269_harvest_skill_receipt_line_in_blockquote():
    text = (ROOT / "common/.grok/skills/harvest/SKILL.md").read_text(encoding="utf-8")
    assert ">    Worker status receipts" in text or "> Worker status receipts" in text


def test_mrb2269_keeps_linked_existing_pr_and_queues_harvest(tmp_path: Path):
    """FR #1812 path still wins; harvest draft failure still queues (no issue)."""

    class LinkAndFail:
        def create_draft_pr(self, *a, **k):
            raise RuntimeError("draft down")

        def create_issue(self, *a, **k):
            raise AssertionError("must not create issue for harvest queue path")

    # linked existing PR short-circuit
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": "SimonBarnett/bobiverse",
            "title": "harvest: PR opened",
            "body": "Session summary:\nhttps://github.com/SimonBarnett/bobiverse/pull/2012",
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, LinkAndFail(), intake_id="in_link2012")
    assert rec.get("state") == "linked_existing_pr"

    class DraftDown:
        def create_draft_pr(self, *a, **k):
            raise RuntimeError("draft down")

        def create_issue(self, *a, **k):
            raise AssertionError("harvest must queue, not issue-fallback")

    err2, norm2 = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": "SimonBarnett/bobiverse",
            "title": "harvest: playbook lesson without pr url",
            "body": "Session summary:\nA real playbook lesson without a pull link",
        }
    )
    assert err2 is None
    with pytest.raises(intake.GitHubDown):
        intake.file_submission(tmp_path, norm2, DraftDown(), intake_id="in_queue_h")
    assert (tmp_path / "intake" / "outbox" / "in_queue_h.json").is_file()
