"""FR #3050: intake DEFAULT_ALLOW_REPOS includes SimonBarnett/trutex (private OK)."""
from __future__ import annotations

from pathlib import Path

import intake

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "common" / "scripts"
TRUTEX = "SimonBarnett/trutex"


def test_default_allow_repos_includes_trutex():
    assert TRUTEX in intake.DEFAULT_ALLOW_REPOS


def test_intake_accepts_trutex_repo():
    err, norm = intake.validate_payload(
        {
            "repo": TRUTEX,
            "kind": "fr",
            "title": "deposco mapping",
            "body": "from plan",
        }
    )
    assert err is None
    assert norm["repo"] == TRUTEX
    assert norm["kind"] == "fr"


def test_harvest_fallback_lists_trutex():
    text = (SCRIPTS / "Invoke-BobiverseHarvest.ps1").read_text(encoding="utf-8-sig")
    assert f"'{TRUTEX}'" in text


def test_webhooks_doc_lists_trutex():
    doc = (ROOT / "jeeves" / "docs" / "webhooks.md").read_text(encoding="utf-8-sig")
    line = [ln for ln in doc.splitlines() if "Current defaults" in ln][0]
    defaults = line.split("retired", 1)[0]
    assert "trutex" in defaults
