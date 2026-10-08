"""FR #3188: !bored must not fan out one GitHub GET per queue row, and must not
fail-closed purge the queue when those lookups fail (403/timeout/5xx).
"""
from __future__ import annotations

import io
import urllib.error
from pathlib import Path
from unittest import mock

import gitclaim


REPO = "SimonBarnett/a-search"


def _home(tmp_path: Path) -> Path:
    h = tmp_path / "chair"
    h.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(h),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return h


def _fr(num: int, *, state: str = "open") -> dict:
    return {
        "repo": REPO,
        "task": "FR",
        "id": f"#{num}",
        "seq": num,
        "ts": "t",
        "line": f"FR {REPO}#{num}",
        "url": f"https://github.com/{REPO}/issues/{num}",
        "title": f"work {num}",
        "state": state,
        "event": "issues",
    }


def _http_403() -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="https://api.github.com/x",
        code=403,
        msg="rate limit",
        hdrs=None,
        fp=io.BytesIO(b""),
    )


def test_offer_focus_top_http_403_purges_zero_of_130(tmp_path: Path):
    """issue_open raising HTTPError(403) must leave the queue unchanged (fail-open)."""
    home = _home(tmp_path)
    rows = [_fr(i) for i in range(1, 131)]
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": rows, "accepted": [], "done": [], "workers": {}},
    )
    before = [dict(r) for r in rows]

    def boom(_repo: str, _num: str):
        raise _http_403()

    st, job = gitclaim.offer_focus_top(
        home, "marchhare-40596", "#marchhare", issue_open=boom
    )
    assert st == "ok"
    assert job is not None
    q = gitclaim._load_queue_unlocked(home)
    left = q.get("unaccepted") or []
    assert len(left) == 130
    assert {r["id"] for r in left} == {r["id"] for r in before}


def test_offer_focus_top_at_most_one_github_call_per_bored(tmp_path: Path):
    """FR #3212: !bored budget is 0 — live issue_open must not dial out at all."""
    home = _home(tmp_path)
    rows = [_fr(i) for i in range(1, 131)]
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": rows, "accepted": [], "done": [], "workers": {}},
    )
    calls: list[tuple[str, str]] = []

    def counting(repo: str, num: str) -> bool:
        calls.append((repo, str(num)))
        return True

    st, job = gitclaim.offer_focus_top(
        home, "marchhare-40596", "#marchhare", issue_open=counting
    )
    assert st == "ok" and job is not None
    assert calls == [], f"expected 0 GitHub calls, got {len(calls)}: {calls[:5]}"
    assert gitclaim.BORED_GITHUB_CALL_BUDGET == 0


def test_offer_focus_top_closed_first_row_purges_only_that_row(tmp_path: Path):
    """Budget 0: live False is never dialed; stamped closed still purges at bulk."""
    home = _home(tmp_path)
    rows = [_fr(1, state="closed"), _fr(2), _fr(3)]
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": rows, "accepted": [], "done": [], "workers": {}},
    )
    calls: list[str] = []

    def open_except_1(_repo: str, num: str) -> bool:
        calls.append(str(num))
        return str(num) != "1"

    st, job = gitclaim.offer_focus_top(
        home, "marchhare-40596", "#marchhare", issue_open=open_except_1
    )
    assert st == "ok"
    assert job is not None
    assert job["id"] == "#2"
    left = {r["id"] for r in (gitclaim._load_queue_unlocked(home).get("unaccepted") or [])}
    assert "#1" not in left
    assert "#2" in left or job["id"] == "#2"
    assert "#3" in left
    assert calls == []


def test_purge_closed_fr_logs_reason_per_row():
    """Every live CLOSED purge must log a reason naming the row (FR #2899 parity)."""
    logged: list[str] = []
    doc = {"unaccepted": [_fr(11), _fr(12)], "accepted": [], "done": []}
    n = gitclaim._purge_closed_fr_unaccepted(
        doc,
        issue_open=lambda _r, num: str(num) != "11",
        log=logged.append,
    )
    assert n == 1
    assert [r["id"] for r in doc["unaccepted"]] == ["#12"]
    assert any(
        "11" in m and ("purge" in m.lower() or "closed" in m.lower()) for m in logged
    ), logged


def test_github_issue_open_checker_raises_on_403(monkeypatch):
    """Production checker must not return False on 403 (that looked like closed)."""
    import gh_filer

    monkeypatch.setattr(gh_filer, "ensure_gh_token_env", lambda: "env")
    monkeypatch.setenv("GH_TOKEN", "fake-token-for-test")

    def fake_urlopen(_req, timeout=8):
        raise _http_403()

    monkeypatch.setattr(gitclaim.urllib.request, "urlopen", fake_urlopen)
    checker = gitclaim.github_issue_open_checker(cache={})
    assert checker is not None
    raised = False
    try:
        checker(REPO, "99")
    except gitclaim.GitHubLookupUnknown as exc:
        raised = True
        assert "403" in str(exc)
    except urllib.error.HTTPError:
        raised = True
    assert raised, "403 must raise unknown — never return False as closed"


def test_irc_bored_is_local_state_only():
    """FR #3212: _git_bored must not pass live GitHub checkers (local stamped state only)."""
    import inspect
    import irc_agent

    src = inspect.getsource(irc_agent.Client._git_bored)
    assert "pr_exists=None" in src
    assert "issue_open=None" in src
    assert "is_pull=None" in src
    # Fresh per-bored dict alone is the wipe amplifier — must stay gone.
    assert "_gh_cache: dict = {}" not in src
    # Live shared-cache checkers must not be wired on the !bored path anymore.
    assert "ISSUE_OPEN_SHARED_CACHE" not in src
    assert "PR_EXISTS_SHARED_CACHE" not in src
