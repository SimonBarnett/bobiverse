# -*- coding: utf-8 -*-
"""FR #9480: multi-machine author_seats → MRB exact-seat only (no machine-id strand)."""
from __future__ import annotations

import bobreport
import gitclaim
import registered_machines


def _home(tmp_path, monkeypatch, machines):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, set(machines))
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    digest = bobreport.empty_digest()
    for mid, workers in machines.items():
        digest["machines"][mid] = bobreport._empty_machine(mid)
        wlist = []
        for item in workers:
            if isinstance(item, tuple):
                pid, state = item
            else:
                pid, state = item, "idle"
            wlist.append({"nick": f"{mid}-{pid}", "state": state})
        digest["machines"][mid]["worker_list"] = wlist
        digest["machines"][mid]["workers"] = {}
    bobreport.save_digest(tmp_path, digest)
    return tmp_path


def _mrb_two_machine_authors() -> dict:
    """Class of #9452 / #9464: implementer + FIX on different machines."""
    return {
        "repo": "SimonBarnett/bobiverse",
        "task": "MRB",
        "id": "#9452",
        "url": "https://github.com/SimonBarnett/bobiverse/pull/9452",
        "author_seat": "redqueen-6400",
        "implementer_seat": "redqueen-6400",
        # On-disk / _coerce_row form is a comma string (append_author_seat).
        "author_seats": "redqueen-6400,flamingo-17160",
        "event": "pull_request",
    }


def test_fr9480_two_machine_authors_sibling_on_either_machine_eligible(
    tmp_path, monkeypatch
):
    """Exact authors blocked; other seats on those machines stay eligible."""
    _home(
        tmp_path,
        monkeypatch,
        {
            "flamingo": [(17160, "idle"), (17068, "idle")],
            "redqueen": [(6400, "idle"), (6564, "idle")],
            # marchhare empty — under old gate nobody could review.
        },
    )
    row = _mrb_two_machine_authors()
    live = gitclaim.live_seat_nicks(tmp_path)
    assert "flamingo-17160" in live and "flamingo-17068" in live
    assert "redqueen-6400" in live and "redqueen-6564" in live
    # Exact author / FIX seats still blocked.
    assert gitclaim.review_blocked_for_author(row, "redqueen-6400", live) is True
    assert gitclaim.review_blocked_for_author(row, "flamingo-17160", live) is True
    # FR #9480: siblings on author machines are eligible (exact-seat only).
    assert gitclaim.review_blocked_for_author(row, "flamingo-17068", live) is False
    assert gitclaim.review_blocked_for_author(row, "redqueen-6564", live) is False


def test_fr9480_single_machine_authors_sibling_allowed_exact_seat(
    tmp_path, monkeypatch
):
    """FR #9574: even when all author_seats share one machine, siblings are eligible."""
    _home(
        tmp_path,
        monkeypatch,
        {
            "flamingo": [(14096, "idle"), (4120, "idle")],
            "redqueen": [(1, "busy")],
        },
    )
    row = {
        "repo": "SimonBarnett/bobiverse",
        "task": "MRB",
        "id": "#9396",
        "url": "https://github.com/SimonBarnett/bobiverse/pull/9396",
        "author_seat": "flamingo-14096",
        "implementer_seat": "flamingo-14096",
        "author_seats": "flamingo-14096,flamingo-9999",  # same machine
        "event": "pull_request",
    }
    live = gitclaim.live_seat_nicks(tmp_path)
    assert gitclaim.review_blocked_for_author(row, "flamingo-14096", live) is True
    assert gitclaim.review_blocked_for_author(row, "flamingo-9999", live) is True
    assert gitclaim.review_blocked_for_author(row, "flamingo-4120", live) is False
    assert gitclaim.review_blocked_for_author(row, "redqueen-1", live) is False


def test_fr9480_offer_reaches_sibling_when_authors_span_machines(tmp_path, monkeypatch):
    """Offer path rebuilds authors via enrich_mrb_author_fields (FIX queue truth)."""
    _home(
        tmp_path,
        monkeypatch,
        {
            "flamingo": [17160, 17068],
            "redqueen": [6400],
        },
    )
    row = {
        "repo": "SimonBarnett/bobiverse",
        "task": "MRB",
        "id": "#9452",
        "url": "https://github.com/SimonBarnett/bobiverse/pull/9452",
        "author_seat": "redqueen-6400",
        "implementer_seat": "redqueen-6400",
        "event": "pull_request",
        "seq": 1,
        "line": "MRB",
        "ts": "t",
        "action": "opened",
    }
    fix_row = {
        "repo": "SimonBarnett/bobiverse",
        "task": "FIX",
        "id": "#9452",
        "url": "https://github.com/SimonBarnett/bobiverse/pull/9452",
        "nick": "flamingo-17160",
        "accepted_by": "flamingo-17160",
        "accepted_ts": "t0",
        "seq": 1,
        "line": "FIX",
        "ts": "t0",
        "event": "pull_request",
        "action": "opened",
    }
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [row], "accepted": [fix_row], "done": []},
    )
    # Exact FIX seat cannot take it (enrich appends flamingo-17160).
    st_fix, _ = gitclaim.offer_focus_top(tmp_path, "flamingo-17160", "#flamingo")
    assert st_fix == "empty"
    # Sibling on flamingo can (FR #9480 multi-machine exact-seat only).
    st_sib, job = gitclaim.offer_focus_top(tmp_path, "flamingo-17068", "#flamingo")
    assert st_sib == "ok" and job["id"] == "#9452"
