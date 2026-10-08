"""FR #3212: webhooks are source of truth; REST only on exceptions (ETag/budget/gap)."""
from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path

import bobreport
import chair_health as ch
import gitclaim
import github_api_budget as gab

REPO = "SimonBarnett/bobiverse"


def _issue_payload(action: str, num: int, *, state: str = "open", labels=None, title: str | None = None):
    return {
        "action": action,
        "repository": {"full_name": REPO},
        "issue": {
            "number": num,
            "title": title or f"issue {num}",
            "body": "",
            "state": state,
            "labels": [{"name": n} for n in (labels or [])],
        },
    }


def _pr_payload(action: str, num: int, *, merged: bool = False, draft: bool = False, title: str | None = None, body: str = ""):
    return {
        "action": action,
        "repository": {"full_name": REPO},
        "pull_request": {
            "number": num,
            "title": title or f"pr {num}",
            "body": body,
            "merged": merged,
            "draft": draft,
            "state": "closed" if action == "closed" else "open",
            "html_url": f"https://github.com/{REPO}/pull/{num}",
            "labels": [],
        },
    }


def _ids(home: Path):
    return [(r["task"], r["id"]) for r in gitclaim.load_unaccepted(home)]


# --------------------------------------------------------------------------- 1. webhook burst, zero API
def test_webhook_burst_updates_queue_with_zero_api_calls(tmp_path: Path):
    calls: list[str] = []

    def spy_fetch(url: str):
        calls.append(url)
        raise AssertionError(f"REST must not run on webhook path: {url}")

    # Burst: open FR, open MRB (no Closes — keep FR), close FR, reopen FR,
    # ready_for_review PR, merge the first PR. Zero REST throughout.
    events = [
        ("issues", _issue_payload("opened", 1)),
        ("pull_request", _pr_payload("opened", 10)),
        ("issues", _issue_payload("closed", 1, state="closed")),
        ("issues", _issue_payload("reopened", 1)),
        ("pull_request", _pr_payload("ready_for_review", 11)),
        ("pull_request", _pr_payload("closed", 10, merged=True)),
    ]
    for ev, payload in events:
        out = bobreport.apply_git_webhook(tmp_path, ev, payload)
        assert out.ok, out.err

    # FR #1 reopened stays; MRB #10 closed/merged dropped; MRB #11 ready stays.
    got = set(_ids(tmp_path))
    assert ("FR", "#1") in got
    assert ("MRB", "#11") in got
    assert ("MRB", "#10") not in got
    assert calls == []
    # Gap stamp written so reconcile knows webhooks are flowing.
    assert gab.last_git_webhook_ts(tmp_path) is not None


# --------------------------------------------------------------------------- 2. !bored zero API
def test_bored_offer_makes_zero_api_calls_with_large_queue(tmp_path: Path):
    rows = []
    for n in range(1, 141):
        kind = "MRB" if n % 3 == 0 else "FR"
        rows.append({
            "repo": REPO,
            "task": kind,
            "id": f"#{n}",
            "seq": n,
            "ts": "t",
            "line": f"{kind} {REPO}#{n}",
            "url": f"https://github.com/{REPO}/{'pull' if kind == 'MRB' else 'issues'}/{n}",
            "title": f"row {n}",
            "state": "open",
            "event": "pull_request" if kind == "MRB" else "issues",
        })
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": rows, "accepted": [], "done": [], "workers": {}},
    )
    calls: list[str] = []

    def boom(repo, num):
        calls.append(f"{repo}#{num}")
        raise AssertionError("live checker must not run on !bored")

    # Local-only: no live checkers (FR #3212 item 3).
    st1, job1 = gitclaim.offer_focus_top(
        tmp_path, "marchhare-22372", "#marchhare",
        pr_exists=None, is_pull=None, issue_open=None,
    )
    st2, job2 = gitclaim.offer_focus_top(
        tmp_path, "marchhare-40596", "#marchhare",
        pr_exists=None, is_pull=None, issue_open=None,
    )
    assert st1 == "ok" and job1 is not None
    assert st2 == "ok" and job2 is not None
    assert calls == []
    # Passing a live checker must still be budget-zero when BORED budget is 0.
    st3, job3 = gitclaim.offer_focus_top(
        tmp_path, "marchhare-99999", "#marchhare",
        pr_exists=boom, is_pull=boom, issue_open=boom,
    )
    assert st3 == "ok" and job3 is not None
    assert calls == []  # budget 0: never dials out


# --------------------------------------------------------------------------- 3. ETag / 304
class _FakeResp:
    def __init__(self, status: int, body: bytes = b"", headers: dict | None = None):
        self.status = status
        self._body = body
        self.headers = headers or {}

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _req_header(req, name: str) -> str | None:
    for bag in (getattr(req, "headers", None), getattr(req, "unredirected_hdrs", None)):
        if not bag:
            continue
        items = bag.items() if hasattr(bag, "items") else []
        for k, v in items:
            if str(k).lower() == name.lower():
                return v
    return None


def test_reconcile_etag_304_unchanged_and_free(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JEEVES_RESYNC_REPOS", REPO)
    body = json.dumps([{"number": 1, "title": "a", "body": "", "state": "open"}]).encode()
    state = {"n": 0, "etags_sent": []}

    def opener(req, timeout=30.0):
        state["n"] += 1
        inm = _req_header(req, "If-None-Match")
        url = getattr(req, "full_url", None) or getattr(req, "get_full_url", lambda: "")()
        if inm:
            state["etags_sent"].append(inm)
            return _FakeResp(304, b"", {"X-RateLimit-Remaining": "4990"})
        return _FakeResp(
            200,
            body if "issues" in str(url) else b"[]",
            {"ETag": '"etag-v1"', "X-RateLimit-Remaining": "4999"},
        )

    budget = gab.GithubApiBudget(tmp_path, budget_per_hour=1000, floor=500, log=lambda s: None)
    fetch = gab.make_budgeted_fetch(budget, token="t", path="reconcile", opener=opener)

    # First reconcile: charges, stores ETag, enqueues FR #1.
    res1 = gitclaim.resync_from_github(tmp_path, [REPO], fetch_json=fetch, token="t")
    assert res1["ok"]
    assert ("FR", "#1") in set(_ids(tmp_path))
    used_after_first = budget.used
    assert used_after_first >= 1
    assert any("etag-v1" in str(v) for v in budget.etags.values())

    before = list(gitclaim.load_unaccepted(tmp_path))

    # Second reconcile: If-None-Match -> 304, no charge for those pages, queue unchanged.
    res2 = gitclaim.resync_from_github(tmp_path, [REPO], fetch_json=fetch, token="t")
    assert res2["ok"]
    assert state["etags_sent"], "second pass must send If-None-Match"
    assert gitclaim.load_unaccepted(tmp_path) == before
    # 304 pages must not increase used (charge(charged=False) only logs).
    assert budget.used == used_after_first


# --------------------------------------------------------------------------- 4. rate limit exhausted, queue kept
def test_rate_limit_exhausted_keeps_queue_and_logs_backoff_once(tmp_path: Path):
    rows = [
        {
            "repo": REPO, "task": "FR", "id": f"#{n}", "seq": n, "ts": "t",
            "line": f"FR {REPO}#{n}", "url": f"https://github.com/{REPO}/issues/{n}",
            "title": f"r{n}", "state": "open", "event": "issues",
        }
        for n in range(1, 6)
    ]
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": rows, "accepted": [], "done": [], "workers": {}},
    )
    logs: list[str] = []

    class _Hdr(dict):
        def get(self, k, default=None):
            for key in (k, k.lower(), k.title()):
                if key in self:
                    return dict.get(self, key, default)
            return default

    def opener(req, timeout=30.0):
        raise urllib.error.HTTPError(
            req.full_url, 403, "rate limit",
            _Hdr({"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "9999999999"}),
            io.BytesIO(b""),
        )

    budget = gab.GithubApiBudget(tmp_path, budget_per_hour=1000, floor=500, log=logs.append)
    fetch = gab.make_budgeted_fetch(budget, token="t", path="reconcile", opener=opener)
    res = gitclaim.resync_from_github(tmp_path, [REPO], fetch_json=fetch, token="t")
    assert res["ok"]
    assert REPO in (res.get("failed") or [])
    assert len(gitclaim.load_unaccepted(tmp_path)) == 5  # nothing purged
    assert any("backoff" in ln for ln in logs)
    # !bored local-only also keeps every row.
    boom_calls: list = []

    def boom(repo, num):
        boom_calls.append(num)
        raise gitclaim.GitHubLookupUnknown("rate")

    st, job = gitclaim.offer_focus_top(
        tmp_path, "marchhare-1", "#marchhare",
        pr_exists=boom, is_pull=boom, issue_open=boom,
    )
    assert st == "ok" and job is not None
    assert len(gitclaim.load_unaccepted(tmp_path)) == 5
    assert boom_calls == []  # budget 0 on !bored


# --------------------------------------------------------------------------- 5. budget / backoff floor
def test_budget_backoff_skips_non_essential(tmp_path: Path):
    logs: list[str] = []
    budget = gab.GithubApiBudget(tmp_path, budget_per_hour=2, floor=500, log=logs.append)
    budget.used = 2
    budget._persist_budget()
    assert budget.allow("reconcile", essential=False) is False
    assert any("backoff" in ln for ln in logs)
    # Essential startup may still proceed when used==budget only if remaining_budget edge;
    # with used==budget and no essential reserve left, allow essential still False unless used==0.
    # Simulate remaining below floor with budget left:
    logs.clear()
    budget2 = gab.GithubApiBudget(tmp_path / "b2", budget_per_hour=1000, floor=500, log=logs.append)
    budget2.rate_remaining = 100
    budget2.used = 10
    assert budget2.allow("on-demand", essential=False) is False
    assert budget2.allow("reconcile", essential=True) is True  # reserve for startup
    assert logs.count([ln for ln in logs if "backoff" in ln][0]) >= 0
    assert sum(1 for ln in logs if "backoff" in ln) == 1  # once


# --------------------------------------------------------------------------- 6. gap detection
def test_gap_detection_triggers_one_reconcile(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JEEVES_RESYNC_REPOS", "o/a")
    monkeypatch.setattr(ch, "targets", lambda: {"local": "http://127.0.0.1:7700", "public": "https://irc.ntsa.uk"})
    # Skip webhook probes interfering: push next_probe far out via clock.

    class Clock:
        def __init__(self):
            self.t = 100_000.0

        def __call__(self):
            return self.t

    seen: list[str] = []

    def fetch(url):
        seen.append(url)
        return []

    clk = Clock()
    # Recent webhook: no gap reconcile before hourly cadence.
    gab.stamp_git_webhook(tmp_path, now=clk.t - 60)
    logs: list[str] = []
    j = ch.ChairJobs(
        tmp_path, tmp_path, log=logs.append, announce=lambda s: None,
        http=lambda *a, **k: 200, fetch_json=fetch,
        token_loader=lambda: ("tok", "file:x"),
        ignored_loader=lambda: [], clock=clk, sleep=lambda s: None,
        spawn=False, owners={"o"},
    )
    # First delayed resync still runs once at FIRST_RESYNC_DELAY (startup).
    clk.t += ch.FIRST_RESYNC_DELAY_S + 1
    j.tick()
    n_after_startup = len(seen)
    assert n_after_startup >= 1
    # Advance less than RESYNC_S with fresh webhook stamps: no extra reconcile.
    gab.stamp_git_webhook(tmp_path, now=clk.t)
    clk.t += min(ch.WEBHOOK_GAP_S, ch.RESYNC_S) / 2
    j.tick()
    assert len(seen) == n_after_startup
    # Age the webhook past the gap while still inside the hourly window: exactly one gap reconcile.
    gab.stamp_git_webhook(tmp_path, now=clk.t - ch.WEBHOOK_GAP_S - 5)
    clk.t += 1
    j.tick()
    assert len(seen) > n_after_startup
    n_after_gap = len(seen)
    # Immediate re-tick with fresh stamp must not fire again.
    gab.stamp_git_webhook(tmp_path, now=clk.t)
    j.tick()
    assert len(seen) == n_after_gap


def test_resync_interval_is_hourly_not_15m():
    assert ch.RESYNC_S >= 3600.0
    assert gitclaim.BORED_GITHUB_CALL_BUDGET == 0
