"""FR #3135: intake allows any SimonBarnett/* repo (drop per-repo allowlist churn)."""
from __future__ import annotations

from pathlib import Path

import intake

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "common" / "scripts"


def test_repo_allowed_any_simonbarnett_product():
    assert intake.repo_allowed("SimonBarnett/foo-bar") is True
    assert intake.repo_allowed("SimonBarnett/any-new-product") is True


def test_repo_allowed_known_products_still():
    for repo in (
        "SimonBarnett/bobiverse",
        "SimonBarnett/a-search",
        "SimonBarnett/trutex",
        "SimonBarnett/skills-visionary",
        "SimonBarnett/agentic_fomprep",
    ):
        assert intake.repo_allowed(repo) is True


def test_repo_denied_other_org():
    assert intake.repo_allowed("evil/x") is False
    assert intake.repo_allowed("OtherOrg/foo") is False


def test_repo_denied_malformed():
    assert intake.repo_allowed("") is False
    assert intake.repo_allowed("nopath") is False
    assert intake.repo_allowed("../evil") is False


def test_validate_payload_allows_new_simonbarnett_product():
    err, norm = intake.validate_payload(
        {
            "repo": "SimonBarnett/foo-bar",
            "kind": "fr",
            "title": "scaffold",
            "body": "from plan",
        }
    )
    assert err is None
    assert norm["repo"] == "SimonBarnett/foo-bar"


def test_validate_payload_denies_other_org():
    err, norm = intake.validate_payload(
        {"repo": "evil/x", "kind": "issue", "title": "t", "body": "b"}
    )
    assert err == "repo_not_allowed"
    assert norm == {}


def test_outbox_drop_allows_simonbarnett_star():
    assert (
        intake.outbox_drop_reason({"repo": "SimonBarnett/new-plan-product", "title": "t"})
        is None
    )
    assert intake.outbox_drop_reason({"repo": "evil/x", "title": "t"}) == "repo_not_allowed"


def test_harvest_flush_uses_simonbarnett_prefix_check():
    text = (SCRIPTS / "Invoke-BobiverseHarvest.ps1").read_text(encoding="utf-8-sig")
    assert "Test-IntakeRepoAllowed" in text or "SimonBarnett/" in text
    assert "FR #3135" in text or "3135" in text


def test_webhooks_doc_mentions_simonbarnett_star():
    doc = (ROOT / "jeeves" / "docs" / "webhooks.md").read_text(encoding="utf-8-sig")
    assert "SimonBarnett/" in doc
    assert "3135" in doc or "any" in doc.lower()
