"""FR #9574: MRB self-exclusion is exact nick only (cross-PID same-machine allowed)."""
from __future__ import annotations

import bobreport
import gitclaim
import registered_machines

REPO = "SimonBarnett/bobiverse"
AUTHOR = "flamingo-17068"
SIBLING = "flamingo-17160"
OTHER = "redqueen-9"


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


def _mrb(implementer: str) -> dict:
    return {
        "repo": REPO,
        "task": "MRB",
        "id": "#9566",
        "url": f"https://github.com/{REPO}/pull/9566",
        "author_seat": implementer,
        "implementer_seat": implementer,
        "author_seats": [implementer],
        "event": "pull_request",
        "seq": 1,
        "line": "MRB",
        "ts": "2026-11-24T11:00:00Z",
        "action": "opened",
        "title": "tip",
        "state": "open",
    }


def test_fr9574_exact_author_refused_cross_pid_allowed(tmp_path, monkeypatch):
    """author flamingo-17068: assign 17160 allow; assign 17068 refuse (even if redqueen free)."""
    _home(
        tmp_path,
        monkeypatch,
        {
            "flamingo": [17068, 17160],
            "redqueen": [9],
        },
    )
    row = _mrb(AUTHOR)
    live = gitclaim.live_seat_nicks(tmp_path)
    free = gitclaim.free_seat_nicks(tmp_path, live)
    assert OTHER in free
    assert gitclaim.review_blocked_for_author(row, AUTHOR, live, free=free) is True
    assert gitclaim.review_blocked_for_author(row, SIBLING, live, free=free) is False
    assert gitclaim.review_blocked_for_author(row, OTHER, live, free=free) is False


def test_fr9574_assign_cross_pid_ok_exact_refused(tmp_path, monkeypatch):
    _home(
        tmp_path,
        monkeypatch,
        {
            "flamingo": [17068, 17160],
            "redqueen": [9],
        },
    )
    row = _mrb(AUTHOR)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    st_sib, why_sib = gitclaim.assign_row(tmp_path, SIBLING, REPO, "MRB", "#9566")
    assert st_sib == "ok", why_sib
    # Reset queue for exact-author refuse.
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [_mrb(AUTHOR)], "accepted": [], "done": []},
    )
    st_me, why_me = gitclaim.assign_row(tmp_path, AUTHOR, REPO, "MRB", "#9566")
    assert st_me == "refused"
    assert "no self-MRB" in str(why_me)
    assert AUTHOR in str(why_me)


def test_fr9574_offer_reaches_cross_pid_sibling(tmp_path, monkeypatch):
    _home(
        tmp_path,
        monkeypatch,
        {
            "flamingo": [17068, 17160],
            "redqueen": [9],
        },
    )
    row = _mrb(AUTHOR)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    st, job = gitclaim.offer_focus_top(tmp_path, SIBLING, "#flamingo")
    assert st == "ok" and job["id"] == "#9566"
