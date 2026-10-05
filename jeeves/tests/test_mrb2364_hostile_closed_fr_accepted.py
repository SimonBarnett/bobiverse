"""Hostile MRB #2364: ACC CLOSED FR purge gaps beyond implementer suite (FR #2361)."""
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


def test_fr_issue_is_closed_fail_open_on_checker_exception():
    row = {"task": "FR", "repo": "o/a", "id": "#9"}

    def boom(r, n):
        raise RuntimeError("gh down")

    assert gitclaim._fr_issue_is_closed(row, issue_open=boom) is False
    assert gitclaim._fr_issue_is_closed(row) is False
    assert (
        gitclaim._fr_issue_is_closed({**row, "state": "closed"}, issue_open=boom)
        is True
    )


def test_purge_closed_fr_accepted_uses_accepted_by_when_nick_missing(tmp_path, monkeypatch):
    home = _home(tmp_path)
    calls = []

    def fake_clear(h, seat, only_if_work_contains=None):
        calls.append((seat, only_if_work_contains))
        return mock.Mock(ok=True)

    monkeypatch.setattr(gitclaim.bobreport, "clear_seat_doing", fake_clear)
    doc = {
        "accepted": [
            {
                "task": "FR",
                "repo": "o/a",
                "id": "#55",
                "state": "closed",
                "accepted_by": "flamingo-99",
            }
        ],
        "done": [],
    }
    assert gitclaim._purge_closed_fr_accepted(doc, home=home) == 1
    assert calls == [("flamingo-99", "55")]


def test_purge_closed_fr_accepted_skips_clear_without_home():
    doc = {
        "accepted": [
            {"task": "FR", "repo": "o/a", "id": "#1", "state": "closed", "nick": "x-1"}
        ],
        "done": [],
    }
    assert gitclaim._purge_closed_fr_accepted(doc, home=None) == 1
    assert doc["accepted"] == []
    assert doc["done"][0]["result"] == "CLOSED"


def test_offer_top_purges_closed_accepted(tmp_path: Path, monkeypatch):
    home = _home(tmp_path)
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    import bobreport
    import registered_machines

    registered_machines.save_registered(home, {"marchhare"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["workers"] = {"40208": {"state": "idle"}}
    bobreport.save_digest(home, digest)
    monkeypatch.setattr(gitclaim, "live_seat_nicks", lambda h: {"marchhare-40208"})
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
                    "title": "open work",
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
                    "nick": "marchhare-1",
                    "accepted_ts": "2026-10-04T22:11:00Z",
                }
            ],
            "done": [],
            "workers": {},
        },
    )
    st, job = gitclaim.offer_top(
        home,
        "marchhare-40208",
        "#marchhare",
        issue_open=lambda r, n: str(n) == "2361",
    )
    assert st == "ok" and job is not None and job["id"] == "#2361"
    q = gitclaim._load_queue_unlocked(home)
    assert all(r.get("id") != "#2340" for r in (q.get("accepted") or []))
    assert any(
        r.get("id") == "#2340" and r.get("result") == "CLOSED"
        for r in (q.get("done") or [])
    )


def test_shared_helper_keeps_mrb_and_open_fr():
    assert gitclaim._fr_issue_is_closed({"task": "MRB", "id": "#1", "state": "closed"}) is False
    assert (
        gitclaim._fr_issue_is_closed(
            {"task": "FR", "repo": "o/a", "id": "#2"},
            issue_open=lambda r, n: True,
        )
        is False
    )
