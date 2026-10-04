"""FR #1585: open PR MRB must survive resync + offer purge despite stale mrb_done.

Symptom: github-resync logged added=N but open PR #1578 vanished from
unaccepted/accepted/done. Cause: keep/append re-queued the open pull, then
``_purge_dead_mrb_unaccepted`` / ``mrb_already_done`` dropped it again because
ledger ``mrb_done`` still held a premature DONE stamp.
"""
from __future__ import annotations

import gitclaim


def _pr(n: int, title: str = "fix: x", body: str = ""):
    return {
        "number": n,
        "title": title,
        "body": body,
        "html_url": f"https://github.com/o/a/pull/{n}",
        "state": "open",
        "user": {"login": "u"},
    }


def _fetch_open_pr_99(url: str):
    if "/pulls" in url and "state=closed" not in url:
        return [_pr(99, title="fix(jeeves): pin ionos", body="Closes o/a#50")]
    if "/issues" in url:
        return []
    return []


def test_purge_keeps_open_mrb_despite_stale_ledger_mrb_done(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim.stamp_mrb_done(tmp_path, "o/a", "#99")
    assert gitclaim.mrb_ledger_done_hold(tmp_path, "o/a", "#99")
    doc = {
        "v": 1,
        "unaccepted": [
            {
                "repo": "o/a",
                "task": "MRB",
                "id": "#99",
                "seq": 1,
                "ts": "t",
                "line": "",
                "url": "https://github.com/o/a/pull/99",
            }
        ],
        "accepted": [],
        "done": [],
    }

    def pr_exists(repo: str, num: str) -> bool:
        return repo == "o/a" and str(num).lstrip("#") == "99"

    n = gitclaim._purge_dead_mrb_unaccepted(doc, pr_exists=pr_exists, home=tmp_path)
    assert n == 0
    assert [r["id"] for r in doc["unaccepted"]] == ["#99"]
    # Stale ledger must not count as done while the pull is still open.
    assert gitclaim.mrb_already_done(
        doc, doc["unaccepted"][0], home=tmp_path, pr_exists=pr_exists
    ) is False


def test_resync_reenqueues_open_mrb_and_clears_stale_mrb_done(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim.stamp_mrb_done(tmp_path, "o/a", "#99")
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [], "done": []},
    )

    res = gitclaim.resync_from_github(tmp_path, ["o/a"], fetch_json=_fetch_open_pr_99)
    assert res.get("ok") is True
    rows = gitclaim.load_unaccepted(tmp_path)
    mrb = [r for r in rows if r.get("task") == "MRB" and r.get("id") == "#99"]
    assert len(mrb) == 1
    assert "pull/99" in str(mrb[0].get("url") or "")
    # Premature DONE stamp must clear so the next !bored purge cannot wipe the row.
    assert gitclaim.mrb_ledger_done_hold(tmp_path, "o/a", "#99") is False

    def pr_exists(repo: str, num: str) -> bool:
        return repo == "o/a" and str(num).lstrip("#") == "99"

    doc = gitclaim.load_queue(tmp_path)
    n = gitclaim._purge_dead_mrb_unaccepted(doc, pr_exists=pr_exists, home=tmp_path)
    assert n == 0
    assert any(r.get("id") == "#99" for r in doc["unaccepted"])


def test_resync_keep_does_not_drop_want_mrb_for_ledger_alone(tmp_path, monkeypatch):
    """Existing unaccepted open-PR MRB stays through keep even if ledger was stamped."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim.stamp_mrb_done(tmp_path, "o/a", "#99")
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "o/a",
                    "task": "MRB",
                    "id": "#99",
                    "seq": 1,
                    "ts": "t",
                    "line": "",
                    "url": "https://github.com/o/a/pull/99",
                    "offered_to": "marchhare-1",
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    gitclaim.resync_from_github(tmp_path, ["o/a"], fetch_json=_fetch_open_pr_99)
    rows = gitclaim.load_unaccepted(tmp_path)
    mrb = [r for r in rows if r.get("id") == "#99"]
    assert len(mrb) == 1
    assert mrb[0].get("offered_to") == "marchhare-1"
