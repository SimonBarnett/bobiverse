"""MRB #2342 hostile: offer_focus_top with live digest must free ionos sibling when marchhare is pinned out.

FR #6569 / #6591: seed liveness via worker_list (FR #4211) and give bobiverse rows an
explicit needs-ionos cue (FR #4512). Bare require_machine stamps are re-inferred empty.
"""
from __future__ import annotations

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines
import pytest


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("JEEVES_OWNER_ACCOUNT", "simon")
    for k in ("JEEVES_FOCUS_MUTATORS", "JEEVES_FOCUS_MUTATOR_ACCOUNTS", "BOB_CHANSERV_EXCLUDE"):
        monkeypatch.delenv(k, raising=False)
    registered_machines.save_registered(
        tmp_path, {"ionos", "win-mpre8vi4u6u", "marchhare"}
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    return tmp_path


def _row(repo, task, num, seq, **kw):
    r = {
        "repo": repo,
        "task": task,
        "id": f"#{num}",
        "seq": seq,
        "ts": f"2026-10-01T10:00:{seq:02d}Z",
        "line": "x",
    }
    r.update(kw)
    return r


def _queue(home, rows):
    gitclaim._write_queue(
        gitclaim.queue_path(home), {"v": 1, "unaccepted": rows, "accepted": []}
    )


def _seed_live(home, machines: dict[str, list[str]]):
    """Seed digest worker_list so live_seat_nicks sees other-machine seats (FR #4211)."""
    doc = bobreport.empty_digest()
    for mid, pids in machines.items():
        doc["machines"][mid] = bobreport._empty_machine(mid)
        doc["machines"][mid]["worker_list"] = [
            {
                "nick": f"{mid}-{pid}",
                "state": "idle",
                "work": "",
                "updated": "2026-10-14T12:00:00Z",
            }
            for pid in pids
        ]
        # Optional legacy mirror; live_seat_nicks prefers nonempty worker_list.
        doc["machines"][mid]["workers"] = {
            pid: {"state": "idle", "nick": f"{mid}-{pid}"} for pid in pids
        }
    bobreport.save_digest(home, doc)


def test_hostile_offer_with_live_marchhare_still_offers_ionos_sibling(_home):
    """MRB exact-seat (FR #2604) frees the sibling; needs-ionos pin excludes marchhare.

    FR #4512: bobiverse rows need a supported pin cue (label), not a bare stamp.
    """
    row = _row(
        "SimonBarnett/bobiverse",
        "MRB",
        2319,
        7,
        require_machine="ionos",
        labels=["needs-ionos"],
        author_seat="win-mpre8vi4u6u-14452",
        implementer_seat="win-mpre8vi4u6u-14452",
        url="https://github.com/SimonBarnett/bobiverse/pull/2319",
    )
    _queue(_home, [row])
    fi.handle_focus_cmd(_home, "hi bobiverse")
    _seed_live(
        _home,
        {
            "win-mpre8vi4u6u": ["14452", "7764"],
            "marchhare": ["40208"],
        },
    )
    live = gitclaim.live_seat_nicks(_home)
    assert "marchhare-40208" in {n.lower() for n in live}
    assert "win-mpre8vi4u6u-7764" in {n.lower() for n in live}

    assert gitclaim.review_blocked_for_author(row, "win-mpre8vi4u6u-14452", live) is True
    assert gitclaim.review_blocked_for_author(row, "win-mpre8vi4u6u-7764", live) is False
    assert gitclaim.row_blocked_for_machine(row, "marchhare-40208") is True
    # Sibling machine match: ionos pin does not block win-mpre8vi4u6u seats.
    assert gitclaim.row_blocked_for_machine(row, "win-mpre8vi4u6u-7764") is False

    status, job = gitclaim.offer_focus_top(
        _home,
        "win-mpre8vi4u6u-7764",
        "#win-mpre8vi4u6u",
        pr_exists=None,
        is_pull=None,
        issue_open=None,
    )
    assert status == "ok"
    assert job is not None
    assert str(job.get("id")) == "#2319"
    assert job.get("offered_to") == "win-mpre8vi4u6u-7764"


def test_hostile_mrb_sibling_ok_when_other_machine_live(_home):
    """FR #2604: MRB exact-seat only — same-machine sibling may take MRB while flamingo is live."""
    row = _row(
        "SimonBarnett/bobiverse",
        "MRB",
        99,
        1,
        # no require_machine — flamingo is also viable
        author_seat="win-mpre8vi4u6u-1",
        implementer_seat="win-mpre8vi4u6u-1",
        url="https://github.com/SimonBarnett/bobiverse/pull/99",
    )
    _queue(_home, [row])
    fi.handle_focus_cmd(_home, "hi bobiverse")
    registered_machines.save_registered(
        _home, {"ionos", "win-mpre8vi4u6u", "flamingo"}
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    _seed_live(
        _home,
        {"win-mpre8vi4u6u": ["1", "2"], "flamingo": ["9"]},
    )
    live = gitclaim.live_seat_nicks(_home)
    assert "flamingo-9" in {n.lower() for n in live}
    assert gitclaim.review_blocked_for_author(row, "win-mpre8vi4u6u-1", live) is True
    assert gitclaim.review_blocked_for_author(row, "win-mpre8vi4u6u-2", live) is False
    status, job = gitclaim.offer_focus_top(
        _home,
        "win-mpre8vi4u6u-2",
        "#win-mpre8vi4u6u",
        pr_exists=None,
        is_pull=None,
        issue_open=None,
    )
    assert status == "ok"
    assert job is not None
    assert job.get("offered_to") == "win-mpre8vi4u6u-2"
