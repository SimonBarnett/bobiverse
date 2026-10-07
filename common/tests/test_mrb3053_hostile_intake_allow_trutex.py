"""MRB #3053 hostile pins: FR #3050 trutex on intake DEFAULT_ALLOW_REPOS (private OK)."""
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
    line = [ln for ln in doc.splitlines() if "Current defaults" in ln][0]
    assert "trutex" in line.split("retired", 1)[0]
    assert "Private repos are allowlist-eligible" in doc or "visibility is not a gate" in doc


def test_mrb3053_plan_git_still_documents_intake_allowlist():
    text = PLAN_SKILL.read_text(encoding="utf-8")
    assert "DEFAULT_ALLOW_REPOS" in text
    assert "repo_not_allowed" in text
