"""FR #1313: MERGED/CLOSED pull numbers must never be offered as FR."""
from __future__ import annotations

from pathlib import Path

import gitclaim


def _home(tmp_path: Path) -> Path:
    h = tmp_path / "chair"
    h.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(h),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return h


def test_fr_row_offerable_rejects_merged_pr_via_is_pull():
    """#1278 class: ambiguous FR title + number that is a MERGED pull."""
    row = {
        "task": "FR",
        "repo": "SimonBarnett/bobiverse",
        "id": "#1278",
        "url": "https://github.com/SimonBarnett/bobiverse/issues/1278",
        "title": "canonical seat nick giveup match",
    }
    # Without checker, structural checks alone may not catch this.
    assert gitclaim.fr_row_offerable(row) is True
    # Open-only checker (WRONG for FR) would leave MERGED offerable:
    open_only = lambda r, n: False  # merged => not open
    assert gitclaim.fr_row_offerable(row, pr_exists=open_only) is True
    # Any-state is_pull rejects:
    is_pull = lambda r, n: str(n) == "1278"
    assert gitclaim.fr_row_offerable(row, is_pull=is_pull) is False


def test_offer_focus_top_skips_merged_pr_number_as_fr(tmp_path: Path, monkeypatch):
    """FR #1313: injected is_pull must purge a MERGED pull number before offering.

    FR #4264 / #3929: production ``BORED_GITHUB_CALL_BUDGET`` is 0 (FR #3188 / #3212),
    so a live ``is_pull`` is never consulted on the !bored path unless the test raises
    the budget. Raise it here so the injected checker is honored; keep production at 0.
    """
    monkeypatch.setattr(gitclaim, "BORED_GITHUB_CALL_BUDGET", 2)
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#1278",
                    "url": "https://github.com/SimonBarnett/bobiverse/issues/1278",
                    "title": "canonical seat nick",
                    "line": "FR #1278",
                    "seq": 1,
                },
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#1313",
                    "url": "https://github.com/SimonBarnett/bobiverse/issues/1313",
                    "title": "chair offered MERGED PR as FR",
                    "line": "FR #1313",
                    "seq": 2,
                },
            ],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    is_pull = lambda r, n: str(n) == "1278"
    st, job = gitclaim.offer_focus_top(
        home, "marchhare-35600", "#marchhare", is_pull=is_pull
    )
    assert st == "ok" and job is not None
    assert job["id"] == "#1313"
    # Purged from unaccepted
    left = {r["id"] for r in gitclaim.load_unaccepted(home)}
    assert "#1278" not in left
    assert "#1313" in left


def test_offer_focus_top_budget0_keeps_ambiguous_fr_when_is_pull_exhausted(
    tmp_path: Path, monkeypatch
):
    """FR #4264: with budget 0, injected is_pull is not called; unknown → still offer.

    Documents fail-open on the !bored path. Merged-PR skip still holds when budget > 0
    (see test_offer_focus_top_skips_merged_pr_number_as_fr).
    """
    monkeypatch.setattr(gitclaim, "BORED_GITHUB_CALL_BUDGET", 0)
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#1278",
                    "url": "https://github.com/SimonBarnett/bobiverse/issues/1278",
                    "title": "canonical seat nick",
                    "line": "FR #1278",
                    "seq": 1,
                },
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#1313",
                    "url": "https://github.com/SimonBarnett/bobiverse/issues/1313",
                    "title": "chair offered MERGED PR as FR",
                    "line": "FR #1313",
                    "seq": 2,
                },
            ],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    calls: list[str] = []

    def is_pull(r, n):
        calls.append(str(n))
        return str(n) == "1278"

    st, job = gitclaim.offer_focus_top(
        home, "marchhare-35600", "#marchhare", is_pull=is_pull
    )
    assert st == "ok" and job is not None
    assert job["id"] == "#1278"
    assert calls == []
    left = {r["id"] for r in gitclaim.load_unaccepted(home)}
    assert "#1278" in left and "#1313" in left


def test_purge_fr_that_are_pulls_drops_row():
    doc = {
        "unaccepted": [
            {"task": "FR", "repo": "o/a", "id": "#1", "title": "real issue"},
            {"task": "FR", "repo": "o/a", "id": "#2", "title": "was a pr"},
            {"task": "MRB", "repo": "o/a", "id": "#3", "url": "https://github.com/o/a/pull/3"},
        ]
    }
    n = gitclaim._purge_fr_that_are_pulls(
        doc, is_pull=lambda r, n: str(n) == "2"
    )
    assert n == 1
    assert [r["id"] for r in doc["unaccepted"]] == ["#1", "#3"]


def test_github_is_pull_checker_any_state(monkeypatch):
    """MERGED pull still counts as a pull for FR gating."""
    import io
    import json
    import urllib.request

    class _Resp:
        status = 200

        def read(self):
            return json.dumps({"state": "closed", "merged": True}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setenv("GH_TOKEN", "x")
    monkeypatch.setattr(
        "gh_filer.ensure_gh_token_env", lambda: "env", raising=False
    )
    # Import path used inside checker
    import gh_filer

    monkeypatch.setattr(gh_filer, "ensure_gh_token_env", lambda: "env")

    def fake_urlopen(req, timeout=8):
        return _Resp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    check = gitclaim.github_is_pull_checker(cache={})
    assert check is not None
    assert check("SimonBarnett/bobiverse", "1278") is True
