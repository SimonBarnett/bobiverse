"""FR #8377: resync must re-add a missing MRB for an open non-draft product PR.

Symptom: open PR #8353 (head fr-8348, green, mergeable) was absent from the MRB
queue while its Closes FR #8348 was correctly superseded. Seats were never offered
the hostile review. Resync (and force-refresh) must re-enqueue the open PR as MRB
and clear a stale mrb_done, while the linked FR stays superseded by the open Closes.
"""
from __future__ import annotations

import gitclaim


def _pr(n: int, title: str, body: str):
    return {
        "number": n,
        "title": title,
        "body": body,
        "html_url": f"https://github.com/o/a/pull/{n}",
        "state": "open",
        "draft": False,
        "user": {"login": "u"},
    }


def _issue(n: int, title: str):
    return {"number": n, "title": title, "state": "open"}


def _fetch(url: str):
    if "/pulls" in url and "state=closed" not in url:
        return [_pr(8353, title="FR #8348: enable Priority", body="Closes o/a#8348")]
    if "/issues" in url:
        return [_issue(8348, "FR #8348: enable Priority")]
    return []


def _empty_queue(home) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [], "done": []},
    )


def test_open_pr_closes_supersedes_fr_and_queues_mrb(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _empty_queue(tmp_path)

    res = gitclaim.resync_from_github(tmp_path, ["o/a"], fetch_json=_fetch)
    assert res.get("ok") is True

    rows = gitclaim.load_unaccepted(tmp_path)
    fr = [r for r in rows if r.get("task") == "FR" and r.get("id") == "#8348"]
    mrb = [r for r in rows if r.get("task") == "MRB" and r.get("id") == "#8353"]
    assert fr == []  # open Closes supersedes the FR (FR #4589)
    assert len(mrb) == 1
    assert "pull/8353" in str(mrb[0].get("url") or "")


def test_force_refresh_resync_readds_missing_mrb(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _empty_queue(tmp_path)
    # Premature mrb_done from a prior PASS must not strand the still-open PR.
    gitclaim.stamp_mrb_done(tmp_path, "o/a", "#8353")
    assert gitclaim.mrb_ledger_done_hold(tmp_path, "o/a", "#8353")

    res = gitclaim.resync_from_github(
        tmp_path, ["o/a"], fetch_json=_fetch, force_refresh=True
    )
    assert res.get("ok") is True

    rows = gitclaim.load_unaccepted(tmp_path)
    mrb = [r for r in rows if r.get("task") == "MRB" and r.get("id") == "#8353"]
    assert len(mrb) == 1
    assert "pull/8353" in str(mrb[0].get("url") or "")
    # Stale mrb_done must clear so the row survives the offer purge (FR #1585).
    assert gitclaim.mrb_ledger_done_hold(tmp_path, "o/a", "#8353") is False


def test_missing_mrb_helper_flags_only_expected_prs(tmp_path):
    doc = {
        "v": 1,
        "unaccepted": [],
        "accepted": [],
        "done": [],
    }
    prs = [
        _pr(8353, "FR #8348: enable Priority", "Closes o/a#8348"),
        {"number": 8888, "title": "harvest: DONE FR", "draft": False},
        {"number": 7777, "title": "fix(mrb-999): x", "draft": False},
    ]
    missing = gitclaim.list_open_prs_missing_mrb(prs, doc, repo="o/a")
    assert [m["number"] for m in missing] == [8353]
    assert gitclaim.open_pr_expects_mrb_or_fix_row(prs[0]) is True
    assert gitclaim.open_pr_expects_mrb_or_fix_row(prs[1]) is False
    assert gitclaim.open_pr_expects_mrb_or_fix_row(prs[2]) is False
