# -*- coding: utf-8 -*-
"""FR #8754 strengthen: Depends-on OPEN on GitHub blocks offer/assign even when
the prerequisite is not in the local FR queue (!bored budget stays 0).
"""
from __future__ import annotations

from pathlib import Path

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines
import pytest


REPO = "SimonBarnett/bobiverse"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    registered_machines.save_registered(tmp_path, {"marchhare", "flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["worker_list"] = [
        {
            "nick": "marchhare-35600",
            "state": "idle",
            "kind": "grok",
            "start_model": "grok-4",
            "configured_model": "grok-4",
            "updated": "2026-10-01T12:00:00Z",
        }
    ]
    bobreport.save_digest(tmp_path, digest)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return tmp_path


def _row(num: int, **kw) -> dict:
    r = {
        "repo": REPO,
        "task": "FR",
        "id": f"#{num}",
        "seq": num + 1000,
        "ts": f"2026-10-01T10:00:{num:02d}Z",
        "line": f"FR {REPO}#{num}",
        "url": f"https://github.com/{REPO}/issues/{num}",
        "title": f"FR {num}",
        "state": "open",
        "body": "",
    }
    r.update(kw)
    return r


def test_depends_issue_open_checker_keeps_test_fake():
    fake = lambda repo, num: True  # noqa: E731
    assert gitclaim.depends_issue_open_checker(fake) is fake


def test_depends_issue_open_checker_unwraps_budgeted():
    budget = gitclaim._GithubCallBudget(0)
    raw = lambda repo, num: False  # noqa: E731
    wrapped = gitclaim._budgeted_github(raw, budget, "issue_open")
    assert getattr(wrapped, "budget", None) is budget
    out = gitclaim.depends_issue_open_checker(wrapped)
    # Unbudgeted replacement (fresh checker or None on import failure in odd envs).
    assert out is not wrapped


def test_offer_skips_when_depend_open_on_github_not_in_queue(home: Path):
    """S1: FR #10 Depends-on #99; #99 not queued; issue_open True → offer later FR."""
    me = "marchhare-35600"
    blocked = _row(10, body="Depends-on: #99\n", seq=1)
    later = _row(11, seq=2)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [blocked, later],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    fi.handle_focus_cmd(home, REPO)

    def issue_open(repo: str, num: str) -> bool:
        # Depend #99 OPEN; child rows also OPEN (FR #9411 unbudgeted closed check).
        assert repo.lower() == REPO.lower()
        return True

    st, job = gitclaim.offer_focus_top(home, me, "#marchhare", issue_open=issue_open)
    assert st == "ok" and job is not None
    assert job["id"] == "#11"
    doc = gitclaim.load_queue(home)
    assert "#10" in {str(r.get("id")) for r in (doc.get("unaccepted") or [])}
    blocked_row = next(r for r in doc["unaccepted"] if r.get("id") == "#10")
    assert not str(blocked_row.get("offered_to") or "").strip()


def test_assign_refuses_when_depend_open_on_github_not_in_queue(home: Path):
    me = "marchhare-35600"
    blocked = _row(10, body="Depends-on: #99\n", seq=1)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [blocked],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )

    def issue_open(repo: str, num: str) -> bool:
        # Child #10 OPEN; depend #99 OPEN.
        n = str(num).lstrip("#")
        return n in {"10", "99"}

    st, why = gitclaim.assign_row(
        home, me, REPO, "FR", "10", issue_open=issue_open
    )
    assert st == "refused"
    assert (
        "depends-open" in str(why)
        or "depends-on open" in str(why)
        or "blocked" in str(why).lower()
    )


def test_offer_allows_when_depend_closed_on_github(home: Path):
    me = "marchhare-35600"
    row = _row(10, body="Depends-on: #99\n", seq=1)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [row],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    fi.handle_focus_cmd(home, REPO)

    def issue_open(repo: str, num: str) -> bool:
        # Depend #99 CLOSED; child #10 must stay OPEN (FR #9411 closed purge).
        return str(num).lstrip("#") != "99"

    st, job = gitclaim.offer_focus_top(home, me, "#marchhare", issue_open=issue_open)
    assert st == "ok" and job is not None
    assert job["id"] == "#10"
