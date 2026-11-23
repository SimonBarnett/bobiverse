"""FR #9401: MRB self-exclusion is machine-id when another machine is live.

Incident: flamingo-4120 accepted MRB for implementer flamingo-14096 while
redqueen was live (busy). Exact-seat-only (FR #2604) allowed the leak.
"""
from __future__ import annotations

import bobreport
import gitclaim
import registered_machines


def _home(tmp_path, monkeypatch, machines):
    """machines: mid -> list of (pid, state) or list of pids (idle)."""
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


def _mrb(implementer: str) -> dict:
    return {
        "repo": "SimonBarnett/bobiverse",
        "task": "MRB",
        "id": "#9396",
        "url": "https://github.com/SimonBarnett/bobiverse/pull/9396",
        "author_seat": implementer,
        "implementer_seat": implementer,
        "event": "pull_request",
    }


def test_fr9401_same_machine_sibling_blocked_when_other_machine_live_busy(
    tmp_path, monkeypatch
):
    """Class of flamingo-4120 / flamingo-14096 with redqueen busy."""
    _home(
        tmp_path,
        monkeypatch,
        {
            "flamingo": [(14096, "idle"), (4120, "idle")],
            "redqueen": [(1, "busy"), (2, "busy")],
        },
    )
    row = _mrb("flamingo-14096")
    live = gitclaim.live_seat_nicks(tmp_path)
    assert "flamingo-14096" in live and "flamingo-4120" in live
    assert "redqueen-1" in live
    assert gitclaim.review_blocked_for_author(row, "flamingo-14096", live) is True
    assert gitclaim.review_blocked_for_author(row, "flamingo-4120", live) is True
    assert gitclaim.review_blocked_for_author(row, "redqueen-1", live) is False


def test_fr9401_offer_skips_same_machine_sibling(tmp_path, monkeypatch):
    _home(
        tmp_path,
        monkeypatch,
        {
            "flamingo": [14096, 4120],
            "redqueen": [9],
        },
    )
    row = _mrb("flamingo-14096")
    row.update({"seq": 1, "line": "MRB", "ts": "t", "action": "opened"})
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    st_fl, _ = gitclaim.offer_focus_top(tmp_path, "flamingo-4120", "#flamingo")
    assert st_fl == "empty"
    st_rq, job = gitclaim.offer_focus_top(tmp_path, "redqueen-9", "#redqueen")
    assert st_rq == "ok" and job["id"] == "#9396"


def test_fr9401_sole_machine_sibling_still_allowed(tmp_path, monkeypatch):
    """FR #5900 / #2604 throughput: sole-box fleets keep same-machine siblings."""
    _home(tmp_path, monkeypatch, {"flamingo": [14096, 4120]})
    row = _mrb("flamingo-14096")
    live = gitclaim.live_seat_nicks(tmp_path)
    assert gitclaim.review_blocked_for_author(row, "flamingo-14096", live) is True
    assert gitclaim.review_blocked_for_author(row, "flamingo-4120", live) is False
