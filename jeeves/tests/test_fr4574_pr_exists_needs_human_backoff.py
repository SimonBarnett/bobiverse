"""FR #4574: needs_human rows must not burn pr_exists; 403 backs off until reset."""
from __future__ import annotations

import io
import json
import urllib.error
from email.message import Message
from pathlib import Path

import gitclaim

REPO = "SimonBarnett/a-search"


def _mrb(num: int, *, needs_human: bool = False) -> dict:
    row = {
        "repo": REPO,
        "task": "MRB",
        "id": f"#{num}",
        "seq": num,
        "ts": "t",
        "line": f"MRB {REPO}#{num}",
        "url": f"https://github.com/{REPO}/pull/{num}",
        "state": "open",
    }
    if needs_human:
        row["needs_human"] = True
    return row


def _fr(num: int) -> dict:
    return {
        "repo": "SimonBarnett/bobiverse",
        "task": "FR",
        "id": f"#{num}",
        "seq": num,
        "ts": "t",
        "line": f"FR SimonBarnett/bobiverse#{num}",
        "url": f"https://github.com/SimonBarnett/bobiverse/issues/{num}",
        "state": "open",
        "title": "offer me",
    }


def _queue(home: Path, rows) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": list(rows), "accepted": [], "done": []},
    )


def test_needs_human_purge_does_not_call_pr_exists(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim.clear_pr_exists_backoff()
    _queue(tmp_path, [_mrb(3527, needs_human=True), _mrb(4565, needs_human=True)])
    calls: list[str] = []

    def pr_exists(repo, num):
        calls.append(f"{repo}#{num}")
        return True

    gitclaim.purge_dead_mrb_rows(tmp_path, pr_exists=pr_exists)
    gitclaim.purge_dead_mrb_rows(tmp_path, pr_exists=pr_exists)
    assert calls == []
    ids = {
        gitclaim._norm_row_id(r.get("id"))
        for r in gitclaim._load_queue_unlocked(tmp_path).get("unaccepted") or []
    }
    assert ids == {"#3527", "#4565"}


def test_403_backs_off_until_reset(monkeypatch):
    gitclaim.clear_pr_exists_backoff()
    now = {"t": 1_000_000.0}
    monkeypatch.setattr(gitclaim, "pr_exists_now", lambda: now["t"])
    calls = {"n": 0}

    def urlopen(req, timeout=8):
        calls["n"] += 1
        hdrs = Message()
        hdrs["X-RateLimit-Remaining"] = "0"
        hdrs["X-RateLimit-Reset"] = "1000300"
        raise urllib.error.HTTPError(
            "https://api.github.com/repos/o/r/pulls/1",
            403,
            "rate",
            hdrs,
            io.BytesIO(b"rate limit"),
        )

    monkeypatch.setattr(gitclaim.urllib.request, "urlopen", urlopen)
    monkeypatch.setenv("GH_TOKEN", "EXAMPLE_TOKEN")
    monkeypatch.setenv("GITHUB_TOKEN", "")

    import sys
    import types

    fake = types.ModuleType("gh_filer")
    fake.ensure_gh_token_env = lambda: "env"
    monkeypatch.setitem(sys.modules, "gh_filer", fake)
    check = gitclaim.github_pr_exists_checker(cache={})
    assert check is not None
    try:
        check("o/r", "1")
    except gitclaim.GitHubLookupUnknown:
        pass
    try:
        check("o/r", "2")
    except gitclaim.GitHubLookupUnknown:
        pass
    assert calls["n"] == 1
    now["t"] = 1_000_200.0
    try:
        check("o/r", "2")
    except gitclaim.GitHubLookupUnknown:
        pass
    assert calls["n"] == 1
    now["t"] = 1_000_301.0
    try:
        check("o/r", "2")
    except gitclaim.GitHubLookupUnknown:
        pass
    assert calls["n"] == 2
    gitclaim.clear_pr_exists_backoff()


def test_open_pr_is_one_call_per_ttl(monkeypatch):
    gitclaim.clear_pr_exists_backoff()
    clock = {"t": 10.0}
    cache = gitclaim.TTLCache(60.0, clock=lambda: clock["t"])
    calls = {"n": 0}

    class _Resp:
        status = 200
        headers = Message()

        def read(self):
            return json.dumps({"state": "open"}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout=8):
        calls["n"] += 1
        return _Resp()

    monkeypatch.setattr(gitclaim.urllib.request, "urlopen", urlopen)
    monkeypatch.setenv("GH_TOKEN", "EXAMPLE_TOKEN")
    monkeypatch.setenv("GITHUB_TOKEN", "")
    import sys
    import types

    fake = types.ModuleType("gh_filer")
    fake.ensure_gh_token_env = lambda: "env"
    monkeypatch.setitem(sys.modules, "gh_filer", fake)
    check = gitclaim.github_pr_exists_checker(cache=cache)
    assert check("o/r", "9") is True
    assert check("o/r", "9") is True
    assert calls["n"] == 1
    clock["t"] = 80.0
    assert check("o/r", "9") is True
    assert calls["n"] == 2
    gitclaim.clear_pr_exists_backoff()


def test_offerable_fr_is_not_blocked_by_needs_human(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _queue(
        tmp_path,
        [_mrb(3527, needs_human=True), _mrb(4565, needs_human=True), _fr(4574)],
    )
    st, job = gitclaim.offer_focus_top(tmp_path, "marchhare-21652", "#marchhare")
    assert st == "ok"
    assert job is not None
    assert str(job.get("id")).lstrip("#") == "4574"
