"""FR #9865: issue_open must pause globally when rate_remaining=0 (no 403 storm)."""
from __future__ import annotations

import io
import sys
import types
import urllib.error
from email.message import Message
from pathlib import Path

import gitclaim
import github_api_budget as gab


def _install_gh_filer(monkeypatch) -> None:
    fake = types.ModuleType("gh_filer")
    fake.ensure_gh_token_env = lambda: "env"
    monkeypatch.setitem(sys.modules, "gh_filer", fake)
    monkeypatch.setenv("GH_TOKEN", "EXAMPLE_TOKEN")
    monkeypatch.setenv("GITHUB_TOKEN", "")


def _http_403(*, remaining: str = "0", reset: str = "1000300") -> urllib.error.HTTPError:
    hdrs = Message()
    hdrs["X-RateLimit-Remaining"] = remaining
    hdrs["X-RateLimit-Reset"] = reset
    hdrs["X-RateLimit-Resource"] = "core"
    return urllib.error.HTTPError(
        "https://api.github.com/repos/o/r/issues/1",
        403,
        "rate",
        hdrs,
        io.BytesIO(b"rate limit"),
    )


def test_fr9865_403_rate_remaining_0_one_network_call_then_pause(monkeypatch, capsys):
    gitclaim.clear_issue_open_backoff()
    now = {"t": 1_000_000.0}
    monkeypatch.setattr(gitclaim, "issue_open_now", lambda: now["t"])
    calls = {"n": 0}

    def urlopen(req, timeout=8):
        calls["n"] += 1
        raise _http_403(remaining="0", reset="1000300")

    monkeypatch.setattr(gitclaim.urllib.request, "urlopen", urlopen)
    _install_gh_filer(monkeypatch)
    check = gitclaim.github_issue_open_checker(cache={})
    assert check is not None

    for num in ("9848", "9849", "9850", "9851", "9830"):
        try:
            check("SimonBarnett/bobiverse", num)
        except gitclaim.GitHubLookupUnknown:
            pass

    assert calls["n"] == 1, "must not storm issue_open after rate_remaining=0"
    assert gitclaim.issue_open_backoff_active() is True

    out = capsys.readouterr().out
    backoff_warns = [ln for ln in out.splitlines() if "issue_open backoff" in ln]
    assert len(backoff_warns) == 1, out
    storm_warns = [
        ln
        for ln in out.splitlines()
        if "issue_open unknown" in ln and "rate_remaining=0" in ln
    ]
    assert len(storm_warns) <= 1, out

    now["t"] = 1_000_200.0
    try:
        check("SimonBarnett/bobiverse", "9857")
    except gitclaim.GitHubLookupUnknown:
        pass
    assert calls["n"] == 1

    now["t"] = 1_000_301.0
    try:
        check("SimonBarnett/bobiverse", "9857")
    except gitclaim.GitHubLookupUnknown:
        pass
    assert calls["n"] == 2
    gitclaim.clear_issue_open_backoff()


def test_fr9865_404_does_not_arm_backoff(monkeypatch):
    gitclaim.clear_issue_open_backoff()
    calls = {"n": 0}

    def urlopen(req, timeout=8):
        calls["n"] += 1
        hdrs = Message()
        hdrs["X-RateLimit-Remaining"] = "4000"
        raise urllib.error.HTTPError(
            "https://api.github.com/repos/o/r/issues/9",
            404,
            "missing",
            hdrs,
            io.BytesIO(b"missing"),
        )

    monkeypatch.setattr(gitclaim.urllib.request, "urlopen", urlopen)
    _install_gh_filer(monkeypatch)
    check = gitclaim.github_issue_open_checker(cache={})
    assert check("o/r", "8") is False
    assert check("o/r", "9") is False
    assert calls["n"] == 2
    assert gitclaim.issue_open_backoff_active() is False
    gitclaim.clear_issue_open_backoff()


def test_fr9865_api_budget_remaining_0_skips_without_network(tmp_path: Path, monkeypatch):
    """Reuse durable ApiBudget: remaining=0 already known => no probe storm."""
    gitclaim.clear_issue_open_backoff()
    # ApiBudget uses wall clock; keep reset in the future relative to time.time().
    import time as _time

    now = {"t": float(_time.time())}
    monkeypatch.setattr(gitclaim, "issue_open_now", lambda: now["t"])
    bud = gab.GithubApiBudget(tmp_path, budget_per_hour=1000, floor=500, log=lambda _s: None)
    bud.rate_remaining = 0
    bud.rate_reset = now["t"] + 600.0
    bud._persist_budget()

    calls = {"n": 0}

    def urlopen(req, timeout=8):
        calls["n"] += 1
        raise AssertionError("must not dial GitHub while ApiBudget rate_remaining=0")

    monkeypatch.setattr(gitclaim.urllib.request, "urlopen", urlopen)
    _install_gh_filer(monkeypatch)
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    check = gitclaim.github_issue_open_checker(home=tmp_path, cache={})
    assert check is not None
    for num in ("1", "2", "3"):
        try:
            check("o/r", num)
        except gitclaim.GitHubLookupUnknown as exc:
            assert "backoff" in str(exc).lower() or "rate" in str(exc).lower()
    assert calls["n"] == 0
    assert gitclaim.issue_open_backoff_active() is True
    gitclaim.clear_issue_open_backoff()


def test_fr9865_multi_issue_purge_path_does_not_storm(tmp_path: Path, monkeypatch, capsys):
    """offer/purge over many FR rows must not fan out 403s when remaining=0."""
    gitclaim.clear_issue_open_backoff()
    now = {"t": 3_000_000.0}
    monkeypatch.setattr(gitclaim, "issue_open_now", lambda: now["t"])
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    calls = {"n": 0}

    def urlopen(req, timeout=8):
        calls["n"] += 1
        raise _http_403(remaining="0", reset="3000600")

    monkeypatch.setattr(gitclaim.urllib.request, "urlopen", urlopen)
    _install_gh_filer(monkeypatch)
    check = gitclaim.github_issue_open_checker(home=tmp_path, cache={})
    rows = [
        {
            "repo": "SimonBarnett/bobiverse",
            "task": "FR",
            "id": f"#{n}",
            "seq": n,
            "ts": "t",
            "line": f"FR SimonBarnett/bobiverse#{n}",
            "url": f"https://github.com/SimonBarnett/bobiverse/issues/{n}",
            "state": "open",
            "title": f"child {n}",
        }
        for n in range(9848, 9858)
    ]
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": rows, "accepted": [], "done": []},
    )
    doc = gitclaim._load_queue_unlocked(tmp_path)
    gitclaim._purge_closed_fr_unaccepted(doc, issue_open=check)
    assert calls["n"] == 1
    out = capsys.readouterr().out
    assert sum(1 for ln in out.splitlines() if "issue_open backoff" in ln) == 1
    gitclaim.clear_issue_open_backoff()
