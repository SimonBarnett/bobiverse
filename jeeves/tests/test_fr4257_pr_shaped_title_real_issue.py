"""FR #4257: fr_row_offerable must not drop real issues with conventional-commit titles.

Title heuristic (_PR_SHAPED_FR_TITLE_RE) applies only when the row is not already
identified as an issues event or /issues/N URL. Real PRs stay filtered via
/pull/ URL, pull_request event, or is_pull True.
"""
from __future__ import annotations

import gitclaim


def test_issues_url_ci_title_stays_offerable():
    """#3975 shape: /issues/N + CI: title must remain offerable."""
    row = {
        "task": "FR",
        "repo": "SimonBarnett/bobiverse",
        "id": "#3975",
        "url": "https://github.com/SimonBarnett/bobiverse/issues/3975",
        "title": "CI: run BOM-less ASCII gates on every PR (not only gitclaim)",
        "state": "open",
    }
    assert gitclaim.fr_row_offerable(row) is True


def test_issues_event_fix_title_stays_offerable():
    row = {
        "task": "FR",
        "repo": "o/r",
        "id": "#42",
        "url": "https://github.com/o/r/issues/42",
        "event": "issues",
        "title": "fix: genuine issue with conventional prefix",
        "state": "open",
    }
    assert gitclaim.fr_row_offerable(row) is True


def test_issues_url_conventional_title_still_rejected_when_is_pull():
    """/issues/N that is actually a PR (#833) still rejected via is_pull."""
    row = {
        "task": "FR",
        "repo": "SimonBarnett/bobiverse",
        "id": "#833",
        "url": "https://github.com/SimonBarnett/bobiverse/issues/833",
        "title": "fix(fr-818): refuse per-PR UAT; only UAT #0 + repo_uat",
        "state": "open",
    }
    assert gitclaim.fr_row_offerable(row) is True  # URL identifies issues; title alone ok
    assert (
        gitclaim.fr_row_offerable(row, is_pull=lambda r, n: str(n) == "833") is False
    )


def test_pull_url_conventional_title_still_rejected():
    row = {
        "task": "FR",
        "repo": "o/r",
        "id": "#10",
        "url": "https://github.com/o/r/pull/10",
        "title": "docs: something",
        "state": "open",
    }
    assert gitclaim.fr_row_offerable(row) is False


def test_pull_request_event_still_rejected():
    row = {
        "task": "FR",
        "repo": "o/r",
        "id": "#11",
        "url": "https://github.com/o/r/issues/11",
        "event": "pull_request",
        "title": "feat: from pr event",
        "state": "open",
    }
    assert gitclaim.fr_row_offerable(row) is False


def test_title_heuristic_still_filters_when_type_unclear():
    """No /issues/ URL and no issues event: conventional title still rejects."""
    row = {
        "task": "FR",
        "repo": "o/r",
        "id": "#99",
        "url": "",
        "title": "ci: looks like a PR title",
        "state": "open",
    }
    assert gitclaim.fr_row_offerable(row) is False
