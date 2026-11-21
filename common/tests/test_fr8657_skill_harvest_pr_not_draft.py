"""FR #8657: offerable skill/harvest tips open non-draft, including file payloads.

docs/intake-harvest-only attachments follow FR #8642 (skill-source, draft false).
Worker receipts and session summaries stay record-only (FR #2650).
"""
from __future__ import annotations

from pathlib import Path

import gitclaim
import intake

REPO = "SimonBarnett/bobiverse"


def test_fr8657_empty_skill_opens_not_draft(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    err, norm = intake.validate_payload(
        {
            "kind": "skill",
            "repo": REPO,
            "title": "skill: pin the chair host before offering",
            "body": "what: fold the chair host before the pin is stored.\n",
            "source": {"skill_book": "harvest", "agent": "plan"},
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_empty8657")
    assert rec["state"] == "filed"
    pr = filer.prs[-1]
    assert pr.get("draft") is False
    paths = [f.get("path") for f in pr.get("files") or []]
    assert paths
    assert not gitclaim.is_intake_harvest_only_paths(paths)


def test_fr8657_skill_file_payload_opens_not_draft(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    err, norm = intake.validate_payload(
        {
            "kind": "skill",
            "repo": REPO,
            "title": "skill: record the chair fold in the book",
            "body": "## Lesson\nFold ionos to walrus before storing require_machine.\n",
            "files": [
                {
                    "path": ".grok/skills/harvest/SKILL.md",
                    "content": "# harvest\n\nFold the chair host before the pin.\n",
                }
            ],
            "source": {"skill_book": "harvest", "agent": "worker"},
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_file8657")
    assert rec["state"] == "filed"
    pr = filer.prs[-1]
    assert pr.get("draft") is False
    paths = [f.get("path") for f in pr.get("files") or []]
    assert paths == [".grok/skills/harvest/SKILL.md"]
    assert not gitclaim.is_intake_harvest_only_paths(paths)


def test_fr8657_harvest_file_payload_opens_not_draft(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": REPO,
            "title": "harvest: chair fold belongs in the lesson file",
            "body": "## Lesson\nStore walrus when the cue says ionos.\n",
            "files": [
                {
                    "path": "common/.grok/skills/harvest/lessons.md",
                    "content": "- Store walrus when the cue says ionos.\n",
                }
            ],
            "source": {"skill_book": "harvest", "agent": "Invoke-BobiverseHarvest"},
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_hv8657")
    assert rec["state"] == "filed"
    pr = filer.prs[-1]
    assert pr.get("draft") is False
    paths = [f.get("path") for f in pr.get("files") or []]
    assert "common/.grok/skills/harvest/lessons.md" in paths
    assert not gitclaim.is_intake_harvest_only_paths(paths)


def test_fr8657_intake_harvest_only_becomes_skill_source(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": REPO,
            "title": "harvest: offer the playbook from the skill book",
            "body": "what: do not leave the tip under docs/intake-harvest.\n",
            "files": [
                {
                    "path": "docs/intake-harvest/intake-in_x.md",
                    "content": "stub only\n",
                }
            ],
            "source": {"skill_book": "harvest", "agent": "worker"},
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_only8657")
    assert rec["state"] == "filed"
    pr = filer.prs[-1]
    assert pr.get("draft") is False
    paths = [f.get("path") for f in pr.get("files") or []]
    assert not gitclaim.is_intake_harvest_only_paths(paths)
    assert any(str(p).startswith("docs/skill-sources/") for p in paths)


def test_fr8657_session_summary_and_pass_receipt_stay_unfiled(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": REPO,
            "title": "harvest: seat finished",
            "body": "Session summary:\nReviewed and left the tip.\n",
            "files": [
                {
                    "path": ".grok/skills/harvest/SKILL.md",
                    "content": "# harvest\n",
                }
            ],
            "source": {"agent": "Invoke-BobiverseHarvest"},
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_sum8657")
    assert rec["state"] == "receipt_recorded"
    assert filer.prs == []

    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": REPO,
            "title": "harvest: DONE FR #1 PASS",
            "body": "Worker receipt. PASS.\n",
            "source": {"agent": "worker"},
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_pass8657")
    assert rec["state"] == "receipt_recorded"
    assert filer.prs == []
