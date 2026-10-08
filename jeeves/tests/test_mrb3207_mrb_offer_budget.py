"""Fix for MRB #3207 FAIL (FR #3188) + FR #3212: MRB rows stay offerable under the
!bored GitHub budget.

FR #3212 sets ``BORED_GITHUB_CALL_BUDGET = 0`` (local-state only on !bored). Cache
hits remain free and may purge; live network calls never run on this path; unknown
rows stay offerable and are never purged.
"""
from __future__ import annotations

import io
import urllib.error
from pathlib import Path

import gitclaim

REPO = "SimonBarnett/a-search"


def _home(tmp_path: Path, rows, accepted=None) -> Path:
    h = tmp_path / "chair"
    h.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(h),
        {"v": 1, "unaccepted": rows, "accepted": accepted or [], "done": [], "workers": {}},
    )
    return h


def _mrb(num: int) -> dict:
    return {
        "repo": REPO, "task": "MRB", "id": f"#{num}", "seq": num, "ts": "t",
        "line": f"MRB {REPO}#{num}", "url": f"https://github.com/{REPO}/pull/{num}",
        "title": f"pr {num}", "state": "open", "event": "pull_request",
    }


def _ids(home: Path) -> list[str]:
    return [r["id"] for r in gitclaim.load_unaccepted(home)]


class _Counting:
    """Stub checker; optional ``cached`` dict exposes a free ``peek`` like the real checkers."""

    def __init__(self, verdict, cached: dict | None = None):
        self.verdict = verdict
        self.calls: list[str] = []
        if cached is not None:
            self.peek = lambda repo, num: cached.get(str(num), gitclaim._CACHE_MISS)

    def __call__(self, repo: str, num: str):
        self.calls.append(str(num))
        v = self.verdict(num) if callable(self.verdict) else self.verdict
        if isinstance(v, BaseException):
            raise v
        return v


def test_one_open_mrb_with_live_pr_exists_is_offered(tmp_path: Path):
    """Budget 0: no live GET; open MRB still offered from local state."""
    home = _home(tmp_path, [_mrb(301)])
    chk = _Counting(True)
    st, job = gitclaim.offer_focus_top(home, "marchhare-22372", "#marchhare", pr_exists=chk)
    assert st == "ok" and job is not None and job["id"] == "#301"
    assert chk.calls == []


def test_offer_top_one_open_mrb_with_live_pr_exists_is_offered(tmp_path: Path):
    home = _home(tmp_path, [_mrb(301)])
    chk = _Counting(True)
    st, job = gitclaim.offer_top(home, "marchhare-22372", "#marchhare", pr_exists=chk)
    assert st == "ok" and job is not None and job["id"] == "#301"
    assert chk.calls == []


def test_budget_used_up_mrb_is_unknown_and_still_offered(tmp_path: Path):
    """Budget 0: every live check is unknown; first row offered, none purged."""
    home = _home(tmp_path, [_mrb(10), _mrb(11), _mrb(12)])
    chk = _Counting(lambda n: n != "10")  # would close #10 if dialed
    st, job = gitclaim.offer_focus_top(home, "marchhare-40596", "#marchhare", pr_exists=chk)
    assert st == "ok" and job["id"] == "#10"
    assert chk.calls == []
    assert _ids(home) == ["#10", "#11", "#12"]


def test_http_403_mrb_is_unknown_offered_and_not_purged(tmp_path: Path):
    err = urllib.error.HTTPError("https://api.github.com/x", 403, "rate limit", None, io.BytesIO(b""))
    rows = [_mrb(n) for n in range(1, 41)]
    home = _home(tmp_path, rows)
    chk = _Counting(err)
    st, job = gitclaim.offer_focus_top(home, "marchhare-40596", "#marchhare", pr_exists=chk)
    assert st == "ok" and job["id"] == "#1"
    assert chk.calls == []
    assert len(_ids(home)) == 40


def test_cache_hits_are_free_against_the_budget(tmp_path: Path, capsys):
    """Cached closed verdicts purge (with reason) without spending a network call."""
    home = _home(tmp_path, [_mrb(1), _mrb(2), _mrb(3), _mrb(4)])
    chk = _Counting(True, cached={"1": False, "2": False, "3": False})
    st, job = gitclaim.offer_focus_top(home, "marchhare-22372", "#marchhare", pr_exists=chk)
    assert st == "ok" and job["id"] == "#4"
    assert chk.calls == []  # #1-#3 cache; #4 would need network but budget=0 -> unknown -> offer
    assert _ids(home) == ["#4"]
    out = capsys.readouterr().out
    for n in (1, 2, 3):
        assert f"INFO git-claim purge dead-mrb {REPO}#{n} reason=pr_exists=False" in out


def test_all_cached_open_costs_zero_network_calls(tmp_path: Path):
    home = _home(tmp_path, [_mrb(n) for n in range(1, 6)])
    chk = _Counting(True, cached={str(n): True for n in range(1, 6)})
    st, job = gitclaim.offer_focus_top(home, "marchhare-22372", "#marchhare", pr_exists=chk)
    assert st == "ok" and job["id"] == "#1"
    assert chk.calls == []


def test_budget_counts_network_not_calls():
    b = gitclaim._GithubCallBudget(0)
    chk = _Counting(True, cached={"7": True})
    wrapped = gitclaim._budgeted_github(chk, b, "pr_exists")
    assert wrapped(REPO, "7") is True and b.used == 0  # cache hit: free
    try:
        wrapped(REPO, "8")
    except gitclaim.GitHubLookupUnknown:
        pass
    else:
        raise AssertionError("budget 0 should refuse network")
    assert chk.calls == []


def test_mrb_row_offerable_unknown_still_offers():
    def unknown(_r, _n):
        raise gitclaim.GitHubLookupUnknown("rate limited")

    assert gitclaim.mrb_row_offerable(_mrb(5), pr_exists=unknown) is True
    assert gitclaim.mrb_row_offerable(_mrb(5), pr_exists=lambda r, n: False) is False


def test_bored_budget_is_zero():
    assert gitclaim.BORED_GITHUB_CALL_BUDGET == 0
