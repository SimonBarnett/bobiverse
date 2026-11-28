# -*- coding: utf-8 -*-
"""FR #8807 / BOB-D3 S1: skip offer when any Depends-on issue is OPEN."""
from __future__ import annotations

from pathlib import Path

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines
import pytest


REPO = "SimonBarnett/bobiverse"
OTHER = "SimonBarnett/other"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Chair home with registered machines + live seats (BOB_DIGEST_HOME for seat roster)."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    registered_machines.save_registered(tmp_path, {"marchhare", "ionos", "flamingo"})
    digest = bobreport.empty_digest()
    for mid, pids in (
        ("marchhare", ("35600", "35601", "35602", "35603", "35604")),
        ("flamingo", ("9",)),
    ):
        digest["machines"][mid] = bobreport._empty_machine(mid)
        digest["machines"][mid]["worker_list"] = [
            {
                "nick": f"{mid}-{p}",
                "state": "idle",
                "kind": "grok",
                "start_model": "grok-4",
                "configured_model": "grok-4",
                "updated": "2026-11-17T12:00:00Z",
            }
            for p in pids
        ]
    bobreport.save_digest(tmp_path, digest)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return tmp_path


def _row(repo: str, task: str, num: int, seq: int | None = None, **kw) -> dict:
    r = {
        "repo": repo,
        "task": task,
        "id": f"#{num}",
        "seq": seq if seq is not None else num + 1000,
        "ts": f"2026-10-01T10:00:{num:02d}Z",
        "line": f"{task} {repo}#{num}",
        "url": f"https://github.com/{repo}/{'pull' if task == 'MRB' else 'issues'}/{num}",
        "title": f"{task} {num}",
        "state": "open",
    }
    r.update(kw)
    return r


def _write(home: Path, *, unaccepted: list[dict], accepted: list[dict] | None = None) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": unaccepted,
            "accepted": list(accepted or []),
            "done": [],
            "workers": {},
        },
    )


def test_fr8807_skips_open_depend_offers_later_fr(home: Path):
    """S1: FR #3 Depends-on #5 (accepted/held) is skipped; FR #9 is offered; #3 stays queued."""
    me = "marchhare-35600"
    other = "marchhare-35601"
    dep = _row(REPO, "FR", 5, seq=1)
    dep["nick"] = other
    dep["accepted_ts"] = "2026-10-01T10:00:00Z"
    blocked = _row(REPO, "FR", 3, seq=2, body="Depends-on: #5\n")
    later = _row(REPO, "FR", 9, seq=3)
    _write(home, unaccepted=[blocked, later], accepted=[dep])
    fi.handle_focus_cmd(home, REPO)

    st, job = gitclaim.offer_focus_top(home, me, "#marchhare")
    assert st == "ok" and job is not None
    assert job["id"] == "#9"

    doc = gitclaim.load_queue(home)
    un_ids = {str(r.get("id")) for r in (doc.get("unaccepted") or [])}
    assert "#3" in un_ids
    blocked_row = next(r for r in doc["unaccepted"] if r.get("id") == "#3")
    assert not str(blocked_row.get("offered_to") or "").strip()


def test_fr8807_any_open_qualified_depend_blocks(home: Path):
    """S1 any-rule: #4 absent + open other#7 in accepted → skip FR with mixed Depends-on."""
    me = "marchhare-35600"
    other_dep = _row(OTHER, "FR", 7, seq=1)
    other_dep["nick"] = "flamingo-9"
    other_dep["accepted_ts"] = "2026-10-01T10:00:00Z"
    blocked = _row(
        REPO,
        "FR",
        3,
        seq=2,
        body="**Depends-on:** #4, SimonBarnett/other#7\n",
    )
    later = _row(REPO, "FR", 9, seq=3)
    _write(home, unaccepted=[blocked, later], accepted=[other_dep])
    fi.handle_focus_cmd(home, REPO)

    st, job = gitclaim.offer_focus_top(home, me, "#marchhare")
    assert st == "ok" and job is not None
    assert job["id"] == "#9"
    doc = gitclaim.load_queue(home)
    assert any(r.get("id") == "#3" for r in doc.get("unaccepted") or [])


def test_fr8807_only_blocked_empty_and_summarize(home: Path):
    """Only-blocked queue → empty; summarize/format carry depends-open."""
    me = "marchhare-35600"
    dep = _row(REPO, "FR", 5, seq=1)
    dep["nick"] = "marchhare-35601"
    dep["accepted_ts"] = "2026-10-01T10:00:00Z"
    blocked = _row(REPO, "FR", 3, seq=2, body="Depends-on: #5\n")
    _write(home, unaccepted=[blocked], accepted=[dep])
    fi.handle_focus_cmd(home, REPO)

    st, job = gitclaim.offer_focus_top(home, me, "#marchhare")
    assert st == "empty" and job is None

    stats = gitclaim.summarize_empty_offer(home, me)
    skips = stats.get("skips") or []
    assert {
        "key": f"FR {REPO}#3",
        "reason": gitclaim.DEPENDS_OPEN_REASON,
    } in skips
    detail = gitclaim.format_empty_offer_detail(me, stats)
    assert gitclaim.DEPENDS_OPEN_REASON in detail


def test_fr8807_issue_open_checker_blocks_absent_dep(home: Path, monkeypatch: pytest.MonkeyPatch):
    """Budgeted issue_open True for cross-repo dep absent from queue → skip, no purge."""
    monkeypatch.setattr(gitclaim, "BORED_GITHUB_CALL_BUDGET", 2)
    me = "marchhare-35600"
    blocked = _row(
        REPO,
        "FR",
        3,
        seq=1,
        body="Depends-on: SimonBarnett/other#77\n",
    )
    later = _row(REPO, "FR", 9, seq=2)
    _write(home, unaccepted=[blocked, later])
    fi.handle_focus_cmd(home, REPO)

    # True = OPEN (do not purge). Cross-repo #77 is open so depends-open blocks #3.
    def issue_open(repo: str, num: str) -> bool:
        return True

    st, job = gitclaim.offer_focus_top(
        home, me, "#marchhare", issue_open=issue_open
    )
    assert st == "ok" and job is not None
    assert job["id"] == "#9"
    left = {r["id"] for r in gitclaim.load_unaccepted(home)}
    assert "#3" in left
    assert "#9" in left  # offered stamp may remain; row not purged


def test_fr8807_none_and_absent_do_not_block(home: Path):
    """Depends-on: (none) and a stamp whose only target is absent → still offered."""
    me = "marchhare-35600"
    none_row = _row(REPO, "FR", 11, seq=1, body="Depends-on: (none)\n")
    absent_row = _row(REPO, "FR", 12, seq=2, body="Depends-on: #40404\n")
    _write(home, unaccepted=[none_row, absent_row])
    fi.handle_focus_cmd(home, REPO)

    st1, j1 = gitclaim.offer_focus_top(home, me, "#marchhare")
    assert st1 == "ok" and j1 is not None
    assert j1["id"] in ("#11", "#12")

    # Clear pin so second offer can proceed.
    with gitclaim._lock(home):
        doc = gitclaim._load_queue_unlocked(home)
        for r in doc.get("unaccepted") or []:
            if str(r.get("id")) == str(j1.get("id")):
                r.pop("offered_to", None)
                r.pop("offered_ts", None)
                r.pop("offered_channel", None)
        # Move first pick to accepted so the other is next.
        kept = []
        for r in doc.get("unaccepted") or []:
            if str(r.get("id")) == str(j1.get("id")):
                r = dict(r)
                r["nick"] = me
                r["accepted_ts"] = gitclaim._utc_now()
                doc.setdefault("accepted", []).append(r)
            else:
                kept.append(r)
        doc["unaccepted"] = kept
        gitclaim._write_queue(gitclaim.queue_path(home), doc)
    gitclaim.clear_seat_hold(home, me, repo=REPO, task="FR", ident=str(j1["id"]))

    st2, j2 = gitclaim.offer_focus_top(home, "marchhare-35601", "#marchhare")
    # FR #10059: Depends-on #40404 is not in the queue and there is no checker,
    # so the row fails closed and is not offered. (none) was the first offer.
    assert j1["id"] == "#11"
    assert st2 == "empty"
    assert j2 is None
