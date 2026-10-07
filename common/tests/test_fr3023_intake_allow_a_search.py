"""FR #3023: intake DEFAULT_ALLOW_REPOS includes SimonBarnett/a-search."""
from __future__ import annotations

from pathlib import Path

import intake

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "common" / "scripts"
ASEARCH = "SimonBarnett/a-search"


def test_default_allow_repos_includes_a_search():
    assert ASEARCH in intake.DEFAULT_ALLOW_REPOS


def test_intake_accepts_a_search_repo():
    err, norm = intake.validate_payload(
        {
            "repo": ASEARCH,
            "kind": "fr",
            "title": "scaffold",
            "body": "from plan",
        }
    )
    assert err is None
    assert norm["repo"] == ASEARCH
    assert norm["kind"] == "fr"


def test_harvest_fallback_lists_a_search():
    text = (SCRIPTS / "Invoke-BobiverseHarvest.ps1").read_text(encoding="utf-8-sig")
    assert f"'{ASEARCH}'" in text


def test_webhooks_doc_lists_a_search():
    doc = (ROOT / "jeeves" / "docs" / "webhooks.md").read_text(encoding="utf-8-sig")
    line = [ln for ln in doc.splitlines() if "Current defaults" in ln][0]
    defaults = line.split("retired", 1)[0]
    assert "a-search" in defaults
