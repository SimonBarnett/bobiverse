"""FR #9478: soft #9401 MRB machine-id (free other-machine) + cross-machine prefer."""
from __future__ import annotations

import sys
from pathlib import Path

import bobreport
import gitclaim
import registered_machines

REPO = Path(__file__).resolve().parents[2]
MON = REPO / "jeeves" / "tools" / "monitor"
SCRIPTS = REPO / "jeeves" / "scripts"
sys.path.insert(0, str(MON))

import mrb_same_machine_starve as starve  # noqa: E402


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
        "id": "#9478",
        "url": "https://github.com/SimonBarnett/bobiverse/pull/9478",
        "author_seat": implementer,
        "implementer_seat": implementer,
        "event": "pull_request",
    }


def test_fr9478_busy_other_machine_allows_same_machine_sibling(tmp_path, monkeypatch):
    """Class of flamingo starve: redqueen busy must not block flamingo sibling."""
    _home(
        tmp_path,
        monkeypatch,
        {
            "flamingo": [17068, 17160],
            "redqueen": [1, 2],
        },
    )
    row = _mrb("flamingo-17068")
    live = gitclaim.live_seat_nicks(tmp_path)
    # Digest coerce resets worker_list state=busy; model busy via free= omit.
    free = {"flamingo-17068", "flamingo-17160"}
    assert "flamingo-17160" in free
    # Soft free=: sibling allowed when other-machine seats are busy-only.
    assert (
        gitclaim.review_blocked_for_author(row, "flamingo-17068", live, free=free)
        is True
    )
    assert (
        gitclaim.review_blocked_for_author(row, "flamingo-17160", live, free=free)
        is False
    )
    # Legacy free=None still treats live as free (busy counts) — call sites must pass free=.
    assert (
        gitclaim.review_blocked_for_author(row, "flamingo-17160", live, free=None)
        is True
    )


def test_fr9478_free_other_machine_still_blocks_sibling(tmp_path, monkeypatch):
    _home(
        tmp_path,
        monkeypatch,
        {
            "flamingo": [17068, 17160],
            "redqueen": [9],
        },
    )
    row = _mrb("flamingo-17068")
    live = gitclaim.live_seat_nicks(tmp_path)
    free = gitclaim.free_seat_nicks(tmp_path, live)
    assert "redqueen-9" in free
    assert (
        gitclaim.review_blocked_for_author(row, "flamingo-17160", live, free=free)
        is True
    )
    assert (
        gitclaim.review_blocked_for_author(row, "redqueen-9", live, free=free) is False
    )


def test_fr9478_offer_focus_top_allows_sibling_when_other_busy(tmp_path, monkeypatch):
    _home(
        tmp_path,
        monkeypatch,
        {
            "flamingo": [17068, 17160],
            "redqueen": [1],
        },
    )
    row = _mrb("flamingo-17068")
    row.update({"seq": 1, "line": "MRB", "ts": "t", "action": "opened"})
    # Mark redqueen accepted so free_seat_nicks excludes it (busy other-machine).
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [row],
            "accepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#1",
                    "nick": "redqueen-1",
                    "seq": 1,
                    "ts": "t",
                    "line": "x",
                }
            ],
            "done": [],
        },
    )
    free = gitclaim.free_seat_nicks(tmp_path, gitclaim.live_seat_nicks(tmp_path))
    assert "redqueen-1" not in {n.lower() for n in free}
    st, job = gitclaim.offer_focus_top(tmp_path, "flamingo-17160", "#flamingo")
    assert st == "ok" and job["id"] == "#9478"


def test_fr9478_prefer_cross_machine_idle_order(tmp_path, monkeypatch):
    _home(
        tmp_path,
        monkeypatch,
        {
            "flamingo": [17068, 17160],
            "redqueen": [9],
        },
    )
    row = _mrb("flamingo-17068")
    row.update({"seq": 1, "line": "MRB", "ts": "t", "action": "opened"})
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    idle = [
        {"nick": "flamingo-17160", "channel": "#flamingo", "told_at": 1.0},
        {"nick": "redqueen-9", "channel": "#redqueen", "told_at": 2.0},
    ]
    ordered = gitclaim.prefer_cross_machine_mrb_reviewers(idle, home=tmp_path)
    assert ordered[0]["nick"] == "redqueen-9"
    assert ordered[1]["nick"] == "flamingo-17160"


def test_fr9478_mrb_offer_nick_prefers_cross_machine(tmp_path, monkeypatch):
    registered_machines.save_registered(tmp_path, {"flamingo", "redqueen"})
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    row = _mrb("flamingo-17068")
    live = {"flamingo-17068", "flamingo-17160", "redqueen-9"}
    free = {"flamingo-17160", "redqueen-9"}
    pick = gitclaim.mrb_offer_nick(
        row, ["flamingo-17160", "redqueen-9"], live, free=free
    )
    assert pick == "redqueen-9"


def test_fr9480_multi_machine_authors_exact_seat_only(tmp_path, monkeypatch):
    """FR #9480: authors on two machines → sibling on either machine is eligible."""
    _home(
        tmp_path,
        monkeypatch,
        {
            "flamingo": [17068, 17160],
            "redqueen": [6400, 6564],
        },
    )
    row = {
        "repo": "SimonBarnett/bobiverse",
        "task": "MRB",
        "id": "#9452",
        "url": "https://github.com/SimonBarnett/bobiverse/pull/9452",
        "author_seat": "redqueen-6400",
        "implementer_seat": "redqueen-6400",
        "author_seats": "redqueen-6400,flamingo-17160",
        "event": "pull_request",
    }
    live = gitclaim.live_seat_nicks(tmp_path)
    free = gitclaim.free_seat_nicks(tmp_path, live)
    # Exact authors still blocked.
    assert (
        gitclaim.review_blocked_for_author(row, "redqueen-6400", live, free=free)
        is True
    )
    assert (
        gitclaim.review_blocked_for_author(row, "flamingo-17160", live, free=free)
        is True
    )
    # Same-machine siblings eligible (exact-seat only when authors span 2+ mids).
    assert (
        gitclaim.review_blocked_for_author(row, "flamingo-17068", live, free=free)
        is False
    )
    assert (
        gitclaim.review_blocked_for_author(row, "redqueen-6564", live, free=free)
        is False
    )


def test_fr9478_monitor_module_wired():
    assert (MON / "mrb_same_machine_starve.py").is_file()
    assert (SCRIPTS / "Test-JeevesMonitorMrbSameMachineStarve.ps1").is_file()
    invoke = (SCRIPTS / "Invoke-JeevesMonitorCheck.ps1").read_text(encoding="utf-8-sig")
    assert "mrb_same_machine_starve" in invoke
    start = (
        REPO / "jeeves" / ".grok" / "skills" / "monitor-start" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "`mrb_same_machine_starve`" in start


def test_fr9478_monitor_ok_when_soft_allows(tmp_path, monkeypatch):
    _home(
        tmp_path,
        monkeypatch,
        {
            "flamingo": [17068, 17160],
            "redqueen": [1],
        },
    )
    row = _mrb("flamingo-17068")
    row.update({"seq": 1, "line": "MRB", "ts": "t", "action": "opened"})
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [row],
            "accepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#1",
                    "nick": "redqueen-1",
                    "seq": 1,
                    "ts": "t",
                    "line": "x",
                }
            ],
            "done": [],
        },
    )
    live = gitclaim.live_seat_nicks(tmp_path)
    free = gitclaim.free_seat_nicks(tmp_path, live)
    cases = starve.collect_starve_cases(
        tmp_path,
        idle_nicks=["flamingo-17160"],
        live=live,
        free=free,
    )
    # Soft free= allows sibling when redqueen busy => no starve finding.
    assert cases == []
