"""MRB #3053 hostile pins: FR #3050 trutex intake (kept under FR #3135 owner gate)."""
from __future__ import annotations

from pathlib import Path

import intake

ROOT = Path(__file__).resolve().parents[2]
TRUTEX = "SimonBarnett/trutex"
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


def test_mrb3053_default_allow_repos_includes_trutex():
    assert TRUTEX in intake.DEFAULT_ALLOW_REPOS


def test_mrb3053_validate_payload_accepts_trutex():
    err, norm = intake.validate_payload(
        {"repo": TRUTEX, "kind": "fr", "title": "deposco", "body": "from plan"}
    )
    assert err is None
    assert norm["repo"] == TRUTEX


def test_mrb3053_harvest_fallback_and_webhooks_private_ok():
    harvest = (ROOT / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1").read_text(
        encoding="utf-8-sig"
    )
    assert f"'{TRUTEX}'" in harvest
    doc = (ROOT / "jeeves" / "docs" / "webhooks.md").read_text(encoding="utf-8-sig")
    assert "trutex" in doc
    assert "Private repos are eligible" in doc or "visibility is not a gate" in doc


def test_mrb3053_plan_git_still_documents_intake_allow():
    text = PLAN_SKILL.read_text(encoding="utf-8")
    assert "SimonBarnett/" in text
    assert "3135" in text or "intake" in text.lower()
