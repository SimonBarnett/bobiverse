"""MRB #3818 hostile pins for FR #3817 case-insensitive queue repo identity."""
from __future__ import annotations

import inspect

import gitclaim
from gitclaim import GitClaim, apply_queue_event, load_unaccepted


CANON = "SimonBarnett/agentic_fomprep"
LOWER = "simonbarnett/agentic_fomprep"


def test_repo_key_and_prefer_casing_helpers():
    assert gitclaim._repo_key(CANON) == gitclaim._repo_key(LOWER)
    assert gitclaim._prefer_repo_casing(LOWER, CANON) == CANON
    assert gitclaim._prefer_repo_casing(CANON, LOWER) == CANON
    assert gitclaim._job_key(LOWER, "fr", "177") == gitclaim._job_key(
        CANON, "FR", "#177"
    )


def test_append_mixed_then_lower_is_duplicate_keeps_git_line(tmp_path):
    apply_queue_event(
        tmp_path,
        GitClaim(
            repo=CANON,
            task="FR",
            id="#177",
            event="issues",
            action="opened",
            line="GIT issues SimonBarnett/agentic_fomprep opened #177",
            title="x",
            state="open",
        ),
    )
    result = apply_queue_event(
        tmp_path,
        GitClaim(
            repo=LOWER,
            task="FR",
            id="#177",
            event="issues",
            action="opened",
            line="",
            title="x",
            state="open",
        ),
    )
    assert result == "duplicate"
    rows = load_unaccepted(tmp_path)
    assert len(rows) == 1
    assert rows[0]["repo"] == CANON
    assert "GIT issues" in str(rows[0].get("line") or "")


def test_collapse_case_variant_twins_prefers_mixed_and_line():
    src = inspect.getsource(gitclaim.collapse_case_variant_twins)
    assert "FR #3817" in src or "_prefer_repo_casing" in src
    doc = {
        "v": 1,
        "unaccepted": [
            {
                "repo": LOWER,
                "task": "FR",
                "id": "#177",
                "line": "",
                "event": "issues",
                "action": "opened",
            },
            {
                "repo": CANON,
                "task": "FR",
                "id": "#177",
                "line": "GIT issues SimonBarnett/agentic_fomprep opened #177",
                "event": "issues",
                "action": "labeled",
            },
        ],
        "accepted": [],
        "done": [],
    }
    dropped = gitclaim.collapse_case_variant_twins(doc)
    assert dropped == 1
    assert len(doc["unaccepted"]) == 1
    assert doc["unaccepted"][0]["repo"] == CANON
    assert "GIT issues" in str(doc["unaccepted"][0].get("line") or "")
