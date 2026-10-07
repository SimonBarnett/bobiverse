"""FR #795: DEFAULT_ALLOW_REPOS examples exclude archived; FR #3135 owner gate supersedes exclusive deny."""
from __future__ import annotations

from pathlib import Path

import intake

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "common" / "scripts"
ARCHIVED = frozenset(
    {
        "SimonBarnett/gh-Jeeves",
        "SimonBarnett/agentic_build",
        "SimonBarnett/AgentMonitor",
        "SimonBarnett/bob-design-uat",
        "SimonBarnett/agentic_irc",
    }
)
LIVE = frozenset(
    {
        "SimonBarnett/bobiverse",
        "SimonBarnett/skills-visionary",
        "SimonBarnett/agentic_fomprep",
        "SimonBarnett/a-search",  # FR #3023
        "SimonBarnett/trutex",  # FR #3050
    }
)


def test_default_allow_repos_excludes_archived_superseded():
    for repo in ARCHIVED:
        assert repo not in intake.DEFAULT_ALLOW_REPOS, repo
    for repo in LIVE:
        assert repo in intake.DEFAULT_ALLOW_REPOS, repo


def test_intake_allows_archived_simonbarnett_under_fr3135_owner_gate():
    """FR #3135: SimonBarnett/* is allowed; queue uses !ignore (not intake deny)."""
    err, norm = intake.validate_payload(
        {
            "repo": "SimonBarnett/gh-Jeeves",
            "kind": "fr",
            "title": "may file; ignore on chair if needed",
            "body": "archived product under owner gate",
        }
    )
    assert err is None
    assert norm["repo"] == "SimonBarnett/gh-Jeeves"


def test_harvest_fallback_mirrors_live_examples_only():
    text = (SCRIPTS / "Invoke-BobiverseHarvest.ps1").read_text(encoding="utf-8-sig")
    assert "'SimonBarnett/bobiverse'" in text
    assert "'SimonBarnett/agentic_fomprep'" in text
    for repo in ARCHIVED:
        assert f"'{repo}'" not in text, repo


def test_webhooks_doc_lists_simonbarnett_star_and_examples():
    doc = (ROOT / "jeeves" / "docs" / "webhooks.md").read_text(encoding="utf-8-sig")
    assert "SimonBarnett/" in doc
    assert "3135" in doc
    assert "bobiverse" in doc
    assert "agentic_fomprep" in doc
    assert "DEFAULT_ALLOW_REPOS" in doc


def test_archived_repos_followup_notes_code_pr():
    doc = (ROOT / "docs" / "ARCHIVED_REPOS.md").read_text(encoding="utf-8-sig")
    assert "Live-reference" in doc or "live-reference" in doc.lower()
    assert "FR #795" in doc or "DEFAULT_ALLOW_REPOS" in doc
    # MRB #808: FR #795 live-reference must not drop the FR #794 archive map.
    assert "## Archived document map (FR #794)" in doc
    assert "docs/archive/" in doc
