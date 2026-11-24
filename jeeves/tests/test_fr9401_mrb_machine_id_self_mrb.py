"""FR #9401 / #9478 / #9574: MRB self-exclusion is exact nick only.

FR #9401 briefly used machine-id sibling block when another machine was free.
FR #9478 softened busy-only other-machine. FR #9574 supersedes both for MRB:
exact author/FIX nick only — cross-PID shop seats on the same machine may review
even when redqueen (or any other machine) has free seats. UAT keeps sibling rules.
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


def test_fr9401_same_machine_sibling_allowed_when_other_machine_free(
    tmp_path, monkeypatch
):
    """FR #9574: free other-machine no longer blocks same-machine MRB sibling."""
    _home(
        tmp_path,
        monkeypatch,
        {
            "flamingo": [(14096, "idle"), (4120, "idle")],
            "redqueen": [(1, "idle"), (2, "idle")],
        },
    )
    row = _mrb("flamingo-14096")
    live = gitclaim.live_seat_nicks(tmp_path)
    free = gitclaim.free_seat_nicks(tmp_path, live)
    assert "flamingo-14096" in live and "flamingo-4120" in live
    assert "redqueen-1" in free
    assert gitclaim.review_blocked_for_author(row, "flamingo-14096", live, free=free) is True
    assert gitclaim.review_blocked_for_author(row, "flamingo-4120", live, free=free) is False
    assert gitclaim.review_blocked_for_author(row, "redqueen-1", live, free=free) is False


def test_fr9478_busy_other_machine_allows_sibling_with_free(tmp_path, monkeypatch):
    """FR #9478 / #9574: sibling allowed regardless of other-machine free/busy."""
    _home(
        tmp_path,
        monkeypatch,
        {
            "flamingo": [14096, 4120],
            "redqueen": [1, 2],
        },
    )
    row = _mrb("flamingo-14096")
    live = gitclaim.live_seat_nicks(tmp_path)
    # Explicit free= (digest coerce drops worker_list busy); redqueen omitted = busy.
    free = {"flamingo-14096", "flamingo-4120"}
    assert "redqueen-1" in live
    assert gitclaim.review_blocked_for_author(row, "flamingo-14096", live, free=free) is True
    assert gitclaim.review_blocked_for_author(row, "flamingo-4120", live, free=free) is False


def test_fr9401_offer_reaches_same_machine_sibling(tmp_path, monkeypatch):
    """FR #9574: offer reaches flamingo sibling even when redqueen is free."""
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
    st_fl, job = gitclaim.offer_focus_top(tmp_path, "flamingo-4120", "#flamingo")
    assert st_fl == "ok" and job["id"] == "#9396"
    # Reset for cross-machine offer still ok.
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    st_rq, job_rq = gitclaim.offer_focus_top(tmp_path, "redqueen-9", "#redqueen")
    assert st_rq == "ok" and job_rq["id"] == "#9396"


def test_fr9401_sole_machine_sibling_still_allowed(tmp_path, monkeypatch):
    """FR #5900 / #2604 / #9574: sole-box fleets keep same-machine siblings."""
    _home(tmp_path, monkeypatch, {"flamingo": [14096, 4120]})
    row = _mrb("flamingo-14096")
    live = gitclaim.live_seat_nicks(tmp_path)
    assert gitclaim.review_blocked_for_author(row, "flamingo-14096", live) is True
    assert gitclaim.review_blocked_for_author(row, "flamingo-4120", live) is False
