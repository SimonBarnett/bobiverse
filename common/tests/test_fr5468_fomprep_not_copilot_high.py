"""FR #5468: agentic_fomprep is not Copilot-high (FR #5186 letter: two repos)."""
from __future__ import annotations

import copilot_dispatch as cd
import focus_ignore as fi


def test_fr5468_high_priority_repos_are_bobiverse_and_a_search_only():
    allowed = {r.lower() for r in fi.HIGH_PRIORITY_REPOS}
    assert allowed == {"simonbarnett/bobiverse", "simonbarnett/a-search"}
    assert not fi.is_high_priority_repo("SimonBarnett/agentic_fomprep")
    assert fi.is_high_priority_repo("SimonBarnett/bobiverse")
    assert fi.is_high_priority_repo("SimonBarnett/a-search")


def test_fr5468_focus_high_cannot_promote_fomprep(tmp_path):
    fi.handle_focus_cmd(tmp_path, "high SimonBarnett/agentic_fomprep")
    doc = fi.load_focus(tmp_path)
    assert fi.repo_priority(doc, "SimonBarnett/agentic_fomprep") != fi.NAMED_PRIORITY["high"]
    assert not cd.is_high_priority(
        tmp_path, {"repo": "SimonBarnett/agentic_fomprep", "task": "FR", "id": "#237"}
    )
