"""FR #2389: an OPEN issue with no merged PR is never withheld from the queue."""
from __future__ import annotations

import gitclaim


def _issue(n, title="FR: x"):
    return {"number": n, "title": title, "html_url": f"https://github.com/o/a/issues/{n}",
            "labels": [{"name": "feature-request"}], "body": "", "user": {"login": "u"}, "pull_request": None,
            "state": "open"}


def _pr(n, title, body):
    return {"number": n, "title": title, "body": body, "html_url": f"https://github.com/o/a/pull/{n}",
            "user": {"login": "u"}, "head": {"ref": "b"}, "state": "open"}


def _fetch(prs, issues):
    def f(url):
        if "page=" in url and "page=1" not in url:
            return []
        if "/pulls" in url and "state=closed" in url:
            return []
        if "/pulls" in url:
            return prs
        if "/issues" in url:
            return issues
        return []
    return f


def _stamp_fr_done(home, key):
    def mut(led):
        led.setdefault("fr_done", {})[key] = gitclaim._utc_now()
    gitclaim._ledger_update(home, mut)


def test_open_issue_closed_only_by_mrb_fix_pr_is_requeued_and_fr_done_cleared(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _stamp_fr_done(tmp_path, gitclaim._lkey("o/a", "#10"))
    fetch = _fetch([_pr(11, "fix(mrb-9): follow-up", "Closes #10")], [_issue(10)])
    gitclaim.resync_from_github(tmp_path, ["o/a"], fetch_json=fetch)
    ids = {(r["task"], r["id"]) for r in gitclaim.load_unaccepted(tmp_path)}
    assert ("FR", "#10") in ids
    led = gitclaim.ledger_load(tmp_path)
    assert gitclaim._lkey("o/a", "#10") not in (led.get("fr_done") or {})


def test_open_issue_with_reviewable_open_pr_is_served_by_mrb_row(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    fetch = _fetch([_pr(11, "fix: real change", "Closes #10")], [_issue(10)])
    gitclaim.resync_from_github(tmp_path, ["o/a"], fetch_json=fetch)
    ids = {(r["task"], r["id"]) for r in gitclaim.load_unaccepted(tmp_path)}
    assert ("MRB", "#11") in ids  # the work is offered as the MRB
    assert ("FR", "#10") not in ids


def test_open_issue_without_any_pr_is_requeued_despite_fr_done(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _stamp_fr_done(tmp_path, gitclaim._lkey("o/a", "#20"))
    gitclaim.resync_from_github(tmp_path, ["o/a"], fetch_json=_fetch([], [_issue(20)]))
    ids = {(r["task"], r["id"]) for r in gitclaim.load_unaccepted(tmp_path)}
    assert ("FR", "#20") in ids


def test_fr_done_cleared_when_open_issue_has_open_closes_pr_but_no_merge(tmp_path, monkeypatch):
    """#2380 class: open Closes-PR means FR stays out of desired, but fr_done must not stick."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _stamp_fr_done(tmp_path, gitclaim._lkey("o/a", "#10"))
    fetch = _fetch([_pr(11, "fix: real change", "Closes #10")], [_issue(10)])
    gitclaim.resync_from_github(tmp_path, ["o/a"], fetch_json=fetch)
    led = gitclaim.ledger_load(tmp_path)
    assert gitclaim._lkey("o/a", "#10") not in (led.get("fr_done") or {})
    ids = {(r["task"], r["id"]) for r in gitclaim.load_unaccepted(tmp_path)}
    assert ("MRB", "#11") in ids
