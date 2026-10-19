"""FR #2361: purge accepted FR rows whose GitHub issue is CLOSED (mirror #2348 unaccepted)."""
from __future__ import annotations

from pathlib import Path
from unittest import mock

import gitclaim


def _home(tmp_path: Path) -> Path:
    h = tmp_path / "chair"
    h.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(h),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return h


def test_purge_closed_fr_accepted_drops_stamped_and_live():
    """FR #4851: nick-held closed ACC stays cancel_pending; orphan ACC still goes to done."""
    doc = {
        "accepted": [
            {
                "task": "FR",
                "repo": "o/a",
                "id": "#1",
                "title": "open",
                "state": "open",
                "nick": "marchhare-1",
            },
            {
                "task": "FR",
                "repo": "o/a",
                "id": "#2340",
                "title": "stamped closed",
                "state": "closed",
                "nick": "marchhare-40208",
            },
            {
                "task": "FR",
                "repo": "o/a",
                "id": "#3",
                "title": "live closed",
                "nick": "flamingo-9",
            },
            {
                "task": "FR",
                "repo": "o/a",
                "id": "#88",
                "title": "orphan closed",
                "state": "closed",
            },
            {
                "task": "MRB",
                "repo": "o/a",
                "id": "#4",
                "url": "https://github.com/o/a/pull/4",
                "nick": "x-1",
            },
        ],
        "done": [],
    }
    n = gitclaim._purge_closed_fr_accepted(
        doc, issue_open=lambda r, num: str(num) != "3"
    )
    assert n == 1  # orphan #88 only
    kept_ids = [r["id"] for r in doc["accepted"]]
    assert kept_ids == ["#1", "#2340", "#3", "#4"]
    for row in doc["accepted"]:
        if row["id"] in ("#2340", "#3"):
            assert row.get("cancel_pending") is True
            assert row.get("state") == "closed"
    done_ids = {r["id"] for r in doc["done"]}
    assert done_ids == {"#88"}
    for fin in doc["done"]:
        assert fin["result"] == "CLOSED"
        assert fin.get("done_ts")


def test_purge_closed_fr_accepted_without_checker_only_stamped():
    doc = {
        "accepted": [
            {"task": "FR", "repo": "o/a", "id": "#1", "state": "closed"},  # orphan
            {"task": "FR", "repo": "o/a", "id": "#2"},  # unknown — keep
            {
                "task": "FR",
                "repo": "o/a",
                "id": "#3",
                "state": "closed",
                "nick": "seat-1",
            },
        ],
        "done": [],
    }
    n = gitclaim._purge_closed_fr_accepted(doc)
    assert n == 1
    assert [r["id"] for r in doc["accepted"]] == ["#2", "#3"]
    assert doc["accepted"][1].get("cancel_pending") is True


def test_purge_closed_fr_accepted_clears_digest_doing_only_matching(tmp_path, monkeypatch):
    """FR #4851: nick-held closed ACC must NOT clear digest (seat still holds ACK)."""
    home = _home(tmp_path)
    calls = []

    def fake_clear(h, seat, only_if_work_contains=None):
        calls.append((str(h), seat, only_if_work_contains))
        return mock.Mock(ok=True)

    monkeypatch.setattr(gitclaim.bobreport, "clear_seat_doing", fake_clear)
    doc = {
        "accepted": [
            {
                "task": "FR",
                "repo": "SimonBarnett/bobiverse",
                "id": "#2340",
                "state": "closed",
                "nick": "marchhare-40208",
            }
        ],
        "done": [],
    }
    n = gitclaim._purge_closed_fr_accepted(doc, home=home)
    assert n == 0
    assert len(doc["accepted"]) == 1
    assert doc["accepted"][0].get("cancel_pending") is True
    assert calls == []


def test_offer_focus_top_purges_closed_accepted_before_pick(tmp_path: Path, monkeypatch):
    home = _home(tmp_path)
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    import bobreport
    import registered_machines

    registered_machines.save_registered(home, {"win-mpre8vi4u6u"})
    digest = bobreport.empty_digest()
    digest["machines"]["win-mpre8vi4u6u"] = bobreport._empty_machine("win-mpre8vi4u6u")
    digest["machines"]["win-mpre8vi4u6u"]["workers"] = {"14452": {"state": "idle"}}
    bobreport.save_digest(home, digest)
    monkeypatch.setattr(gitclaim, "live_seat_nicks", lambda h: {"win-mpre8vi4u6u-14452"})
    monkeypatch.setattr(gitclaim, "ledger_load", lambda h: {})
    monkeypatch.setattr(gitclaim, "worker_working_on", lambda h, n: "")

    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#2361",
                    "url": "https://github.com/SimonBarnett/bobiverse/issues/2361",
                    "title": "purge closed accepted",
                    "line": "FR #2361",
                    "seq": 1,
                    "state": "open",
                }
            ],
            "accepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#2340",
                    "url": "https://github.com/SimonBarnett/bobiverse/issues/2340",
                    "title": "already closed",
                    "nick": "marchhare-40208",
                    "accepted_ts": "2026-10-04T22:11:00Z",
                    # FR #4624 / budget-0: stamped closed is purged offline (no live issue_open).
                    "state": "closed",
                }
            ],
            "done": [],
            "workers": {},
        },
    )
    issue_open = lambda r, n: str(n) == "2361"
    st, job = gitclaim.offer_focus_top(
        home, "win-mpre8vi4u6u-14452", "#win-mpre8vi4u6u", issue_open=issue_open
    )
    assert st == "ok" and job is not None and job["id"] == "#2361"
    q = gitclaim._load_queue_unlocked(home)
    # FR #4851: nick-held closed ACC stays until NACK (cancel_pending), not moved to done.
    held = [r for r in (q.get("accepted") or []) if r.get("id") == "#2340"]
    assert len(held) == 1
    assert held[0].get("cancel_pending") is True
    assert held[0].get("state") == "closed"
    assert not any(
        r.get("id") == "#2340" and r.get("result") == "CLOSED"
        for r in (q.get("done") or [])
    )
