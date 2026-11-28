"""FR #10234: a twin FR whose cited fix PR is already MERGED must not be offered."""
from __future__ import annotations

from pathlib import Path

import gitclaim

REPO = "SimonBarnett/bobiverse"
TWIN_TITLE = "Twin FR #10218 offered after fix merged (FR #10115 twin, PR #1278/#1298)"
TWIN_BODY = (
    "Chair assigned FR #10218 (twin of closed #10115) though PR #1278 and #1298 "
    "already merged on main."
)


def _home(tmp_path: Path) -> Path:
    h = tmp_path / "chair"
    h.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(h),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return h


def test_twin_cue_with_merged_cited_pr_is_skipped():
    merged = lambda r, n: str(n) == "1278"
    reason = gitclaim.fr_twin_cited_merged_pr_reason(
        TWIN_TITLE, TWIN_BODY, REPO, is_merged=merged
    )
    assert reason == "twin-merged-pr: PR #1278 already merged"


def test_twin_cue_with_open_cited_pr_stays_offerable():
    not_merged = lambda r, n: False
    assert (
        gitclaim.fr_twin_cited_merged_pr_reason(
            TWIN_TITLE, TWIN_BODY, REPO, is_merged=not_merged
        )
        is None
    )


def test_ordinary_fr_citing_merged_pr_without_cue_is_offerable():
    """A real FR that merely references a merged PR (no twin cue) is not skipped."""
    merged = lambda r, n: True
    assert (
        gitclaim.fr_twin_cited_merged_pr_reason(
            "Follow up on PR #1278 behaviour",
            "Builds on PR #1278 which we want to extend with a new flag.",
            REPO,
            is_merged=merged,
        )
        is None
    )


def test_lookup_error_fails_open():
    def boom(r, n):
        raise gitclaim.GitHubLookupUnknown("http=503")

    assert (
        gitclaim.fr_twin_cited_merged_pr_reason(
            TWIN_TITLE, TWIN_BODY, REPO, is_merged=boom
        )
        is None
    )


def test_no_network_lookup_for_rows_without_twin_cue():
    calls: list[str] = []

    def spy(r, n):
        calls.append(str(n))
        return True

    row = {
        "task": "FR",
        "repo": REPO,
        "id": "#42",
        "url": "https://github.com/SimonBarnett/bobiverse/issues/42",
        "title": "Add a flag",
        "body": "Plain feature request with no twin language.",
    }
    assert gitclaim.row_fr_twin_merged_reason(row, pr_merged=spy) is None
    assert calls == []


def test_offer_focus_top_skips_twin_fr_and_offers_next(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(gitclaim, "BORED_GITHUB_CALL_BUDGET", 0)
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": REPO,
                    "task": "FR",
                    "id": "#10218",
                    "url": "https://github.com/SimonBarnett/bobiverse/issues/10218",
                    "title": TWIN_TITLE,
                    "body": TWIN_BODY,
                    "line": "FR #10218",
                    "seq": 1,
                },
                {
                    "repo": REPO,
                    "task": "FR",
                    "id": "#10300",
                    "url": "https://github.com/SimonBarnett/bobiverse/issues/10300",
                    "title": "Real open feature",
                    "body": "No twin here.",
                    "line": "FR #10300",
                    "seq": 2,
                },
            ],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    merged = lambda r, n: str(n) == "1278"
    st, job = gitclaim.offer_focus_top(
        home, "marchhare-35600", "#marchhare", pr_merged=merged
    )
    assert st == "ok" and job is not None
    assert job["id"] == "#10300"
    left = {r["id"] for r in gitclaim.load_unaccepted(home)}
    assert "#10218" not in left
    assert "#10300" in left
