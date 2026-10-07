"""FR #795: intake allow-list and harvest fallback drop archived superseded repos."""
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
    }
)


def test_default_allow_repos_excludes_archived_superseded():
    for repo in ARCHIVED:
        assert repo not in intake.DEFAULT_ALLOW_REPOS, repo
    for repo in LIVE:
        assert repo in intake.DEFAULT_ALLOW_REPOS, repo


def test_intake_rejects_archived_gh_jeeves():
    err, norm = intake.validate_payload(
        {
            "repo": "SimonBarnett/gh-Jeeves",
            "kind": "fr",
            "title": "should not file here",
            "body": "archived",
        }
    )
    assert err == "repo_not_allowed"
    assert norm == {}


def test_harvest_fallback_mirrors_live_allowlist_only():
    text = (SCRIPTS / "Invoke-BobiverseHarvest.ps1").read_text(encoding="utf-8-sig")
    # Fallback block must not list archived repos (parser may miss intake.py).
    assert "'SimonBarnett/bobiverse'" in text
    assert "'SimonBarnett/agentic_fomprep'" in text
    for repo in ("gh-Jeeves", "agentic_build", "AgentMonitor", "bob-design-uat", "agentic_irc"):
        assert f"SimonBarnett/{repo}" not in text or f"'SimonBarnett/{repo}'" not in text
    # Stronger: none of the archived full names appear as quoted fallback entries.
    for repo in ARCHIVED:
        assert f"'{repo}'" not in text, repo


def test_webhooks_doc_lists_live_allowlist_only():
    doc = (ROOT / "jeeves" / "docs" / "webhooks.md").read_text(encoding="utf-8-sig")
    assert "DEFAULT_ALLOW_REPOS" in doc
    assert "bobiverse" in doc
    assert "agentic_fomprep" in doc
    line = [ln for ln in doc.splitlines() if "Current defaults" in ln][0]
    # Defaults portion (before any "retired" note) must not list archived repos.
    defaults = line.split("retired", 1)[0]
    assert "`SimonBarnett/bobiverse`" in defaults or "bobiverse" in defaults
    for needle in ("`gh-Jeeves`", "`agentic_build`", "`AgentMonitor`", "`bob-design-uat`"):
        assert needle not in defaults, needle
    assert "FR #795" in line


def test_archived_repos_followup_notes_code_pr():
    doc = (ROOT / "docs" / "ARCHIVED_REPOS.md").read_text(encoding="utf-8-sig")
    assert "Live-reference" in doc or "live-reference" in doc.lower()
    assert "FR #795" in doc or "DEFAULT_ALLOW_REPOS" in doc
    # MRB #808: FR #795 live-reference must not drop the FR #794 archive map.
    assert "## Archived document map (FR #794)" in doc
    assert "docs/archive/" in doc
