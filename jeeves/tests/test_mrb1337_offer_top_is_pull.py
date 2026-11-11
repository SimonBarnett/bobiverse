"""Hostile MRB #1337: offer_top must accept is_pull (FR #1313 wiring).

FR #6568: production offer budget is deliberately zero (FR #3212). A plain
callable ``is_pull`` never runs, so purge pins must supply a free ``peek``
cache hit (same pattern as MRB #3207 / FR #1313).
"""
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


def _two_fr_rows() -> list[dict]:
    return [
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
            "title": "real fr",
            "line": "FR #1313",
            "seq": 2,
        },
    ]


class _CachedIsPull:
    """Callable is_pull with free peek (budget-zero definitive verdicts)."""

    def __init__(self, cached: dict | None = None):
        self.calls: list[str] = []
        self._cached = {str(k): bool(v) for k, v in (cached or {}).items()}

    def peek(self, repo: str, num: str):
        del repo
        key = str(num)
        if key in self._cached:
            return self._cached[key]
        return gitclaim._CACHE_MISS

    def __call__(self, repo: str, num: str) -> bool:
        del repo
        self.calls.append(str(num))
        key = str(num)
        if key in self._cached:
            return self._cached[key]
        return False


def _isolate_digest(tmp_path: Path, monkeypatch) -> Path:
    """FR #6523: suite-mode digest home so queue writes stay under tmp_path."""
    digest = tmp_path / "digest"
    digest.mkdir()
    monkeypatch.setenv("BOBIVERSE_BUILD_SUITE", "1")
    monkeypatch.setenv("BOB_DIGEST_HOME", str(digest))
    return digest


def test_offer_top_accepts_is_pull_and_purges_merged_pr_number(
    tmp_path: Path, monkeypatch
):
    """Cached is_pull=True purges merged PR-shaped FR at budget zero (FR #6568)."""
    _isolate_digest(tmp_path, monkeypatch)
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": _two_fr_rows(),
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    # Any-state PR detector: #1278 is a PR (purge), #1313 is a plain issue.
    # Peek supplies definitive verdicts without spending the zero offer budget.
    is_pull = _CachedIsPull({"1278": True, "1313": False})
    st, job = gitclaim.offer_top(home, "marchhare-1", "#marchhare", is_pull=is_pull)
    assert is_pull.calls == []
    assert st == "ok" and job is not None
    assert job["id"] == "#1313"
    left = gitclaim.load_unaccepted(home)
    assert {r["id"] for r in left} == {"#1313"}
    assert left[0].get("offered_to") == "marchhare-1"
    assert not left[0].get("accepted")


def test_offer_top_unknown_is_pull_preserves_rows_at_budget_zero(
    tmp_path: Path, monkeypatch
):
    """Cache miss => unknown verdict; zero-budget offer must not purge (FR #6568)."""
    _isolate_digest(tmp_path, monkeypatch)
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": _two_fr_rows(),
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    is_pull = _CachedIsPull({})  # every peek is _CACHE_MISS
    st, job = gitclaim.offer_top(home, "marchhare-1", "#marchhare", is_pull=is_pull)
    assert is_pull.calls == []
    assert st == "ok" and job is not None
    assert job["id"] == "#1278"
    left = {r["id"] for r in gitclaim.load_unaccepted(home)}
    assert left == {"#1278", "#1313"}


def test_offer_top_without_is_pull_kw_does_not_nameerror(tmp_path: Path):
    """Regression: body referenced is_pull before the kw existed (MRB #1337)."""
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "o/a",
                    "task": "FR",
                    "id": "#9",
                    "url": "https://github.com/o/a/issues/9",
                    "title": "plain issue",
                    "seq": 1,
                }
            ],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    st, job = gitclaim.offer_top(home, "n-1", "#n")
    assert st == "ok"
    assert job["id"] == "#9"


def test_assign_row_refuses_fr_that_is_pull(tmp_path: Path, monkeypatch):
    import bobreport
    import registered_machines

    digest = tmp_path / "digest"
    digest.mkdir()
    monkeypatch.setenv("BOB_DIGEST_HOME", str(digest))
    registered_machines.save_registered(digest, {"marchhare", "win-mpre8vi4u6u"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None

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
                    "title": "was a pr",
                    "seq": 1,
                }
            ],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    st, res = gitclaim.assign_row(
        home,
        "marchhare-12345",
        "SimonBarnett/bobiverse",
        "FR",
        "#1278",
        is_pull=lambda r, n: str(n) == "1278",
    )
    assert st == "refused"
    assert "pull" in str(res).lower()
