"""MRB #3028 hostile pins: FR #3023 a-search intake (kept under FR #3135 owner gate)."""
from __future__ import annotations

from pathlib import Path

import intake

ROOT = Path(__file__).resolve().parents[2]
ASEARCH = "SimonBarnett/a-search"
PLAN_SKILL = (
    ROOT
    / "bob"
    / "agents"
    / "plan"
    / ".grok"
    / "skills"
    / "plan-git-from-plan"
    / "SKILL.md"
)


def test_mrb3028_default_allow_repos_includes_a_search():
    assert ASEARCH in intake.DEFAULT_ALLOW_REPOS


def test_mrb3028_validate_payload_accepts_a_search():
    err, norm = intake.validate_payload(
        {"repo": ASEARCH, "kind": "fr", "title": "scaffold", "body": "from plan"}
    )
    assert err is None
    assert norm["repo"] == ASEARCH


def test_mrb3028_harvest_fallback_and_webhooks_doc():
    harvest = (ROOT / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1").read_text(
        encoding="utf-8-sig"
    )
    assert f"'{ASEARCH}'" in harvest
    doc = (ROOT / "jeeves" / "docs" / "webhooks.md").read_text(encoding="utf-8-sig")
    assert "a-search" in doc
    assert "SimonBarnett/" in doc


def test_mrb3028_plan_git_documents_intake_allow():
    raw = PLAN_SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "SimonBarnett/" in text
    assert "3135" in text or "3023" in text or "intake" in text.lower()
