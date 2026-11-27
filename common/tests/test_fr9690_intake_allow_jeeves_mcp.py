"""FR #9690: intake DEFAULT_ALLOW_REPOS includes SimonBarnett/jeeves-mcp."""
from __future__ import annotations

from pathlib import Path

import intake

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "common" / "scripts"
JEEVES_MCP = "SimonBarnett/jeeves-mcp"


def test_default_allow_repos_includes_jeeves_mcp():
    assert JEEVES_MCP in intake.DEFAULT_ALLOW_REPOS


def test_intake_accepts_jeeves_mcp_repo():
    err, norm = intake.validate_payload(
        {
            "repo": JEEVES_MCP,
            "kind": "fr",
            "title": "scaffold",
            "body": "from plan",
        }
    )
    assert err is None
    assert norm["repo"] == JEEVES_MCP
    assert norm["kind"] == "fr"


def test_harvest_fallback_lists_jeeves_mcp():
    text = (SCRIPTS / "Invoke-BobiverseHarvest.ps1").read_text(encoding="utf-8-sig")
    assert f"'{JEEVES_MCP}'" in text


def test_webhooks_doc_lists_jeeves_mcp():
    doc = (ROOT / "jeeves" / "docs" / "webhooks.md").read_text(encoding="utf-8-sig")
    assert "jeeves-mcp" in doc
    assert "SimonBarnett/" in doc
