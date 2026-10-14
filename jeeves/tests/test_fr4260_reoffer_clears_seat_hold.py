"""FR #4260: re-offer / other-seat completion clears the original seat's hold.

When seat A is offered a row and never ACKs, then the row is re-offered to seat B
(who completes it), seat A must not stay ``busy (held ...)`` forever so ``!assign``
to A can succeed.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines
import pytest

REPO = "SimonBarnett/bobiverse"
A = "marchhare-8824"
B = "marchhare-11780"
SHOP = "#marchhare"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    registered_machines.save_registered(tmp_path, {"marchhare", "ionos", "flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["workers"] = {
        "8824": {"state": "idle"},
        "11780": {"state": "idle"},
    }
    bobreport.save_digest(tmp_path, digest)
    _queue(tmp_path, [])
    fi.handle_focus_cmd(tmp_path, REPO)
    return tmp_path


def _ts(ago_s: float) -> str:
    t = datetime.now(timezone.utc) - timedelta(seconds=ago_s)
    return t.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _row(task: str, num: int, **kw) -> dict:
    r = {
        "repo": REPO,
        "task": task,
        "id": f"#{num}",
        "seq": num,
        "ts": "2026-10-14T20:00:00Z",
        "line": f"{task} {REPO}#{num}",
        "url": f"https://github.com/{REPO}/{'pull' if task == 'MRB' else 'issues'}/{num}",
        "title": f"{task} {num}",
        "state": "open",
    }
    r.update(kw)
    return r


def _queue(home: Path, unaccepted: list[dict], accepted: list[dict] | None = None) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": unaccepted, "accepted": accepted or [], "done": [], "workers": {}},
    )


def test_reoffer_to_other_seat_clears_original_hold(home: Path):
    """Acceptance 1: re-offer clears the original seat's hold."""
    row = _row("MRB", 1858)
    _queue(home, [row])
    st, job = gitclaim.offer_focus_top(home, A, SHOP, now=time.time())
    assert st == "ok" and job is not None
    assert gitclaim.seat_open_job(home, A).startswith("held MRB") or gitclaim.seat_open_job(
        home, A
    ).startswith("offered MRB")
    # Expire A's offer window so B can take the row.
    doc = gitclaim._load_queue_unlocked(home)
    for cand in doc.get("unaccepted") or []:
        if str(cand.get("id") or "") == "#1858":
            cand["offered_ts"] = _ts(9999)
            cand["offered_via"] = ""  # plain !bored window
    gitclaim._write_queue(gitclaim.queue_path(home), doc)
    st2, job2 = gitclaim.offer_focus_top(home, B, SHOP, now=time.time())
    assert st2 == "ok" and job2 is not None
    assert gitclaim._seat_key(str(job2.get("offered_to") or "")) == gitclaim._seat_key(B)
    # Original seat must be free (hold cleared on re-offer).
    assert gitclaim.seat_open_job(home, A) == ""
    holds = gitclaim._load_seat_holds_unlocked(home)
    assert gitclaim._seat_key(A) not in holds


def test_other_seat_done_clears_original_hold_and_assign_succeeds(home: Path):
    """Acceptance 2: after another seat completes, !assign to the first seat succeeds."""
    # Leftover hold on A with no live offered_to pin (row already left A's pin).
    _queue(home, [_row("MRB", 1858)])
    gitclaim.note_seat_hold(
        home,
        A,
        {"repo": REPO, "task": "MRB", "id": "#1858", "offered_ts": _ts(120)},
    )
    assert "held" in gitclaim.seat_open_job(home, A)
    # B completes the same job key -> clear all seats holding that job.
    cleared = gitclaim.clear_job_seat_holds(home, REPO, "MRB", "#1858")
    assert cleared is True
    assert gitclaim.seat_open_job(home, A) == ""
    # A fresh row can be !assign'd to A.
    _queue(home, [_row("MRB", 4193)])
    status, msg = gitclaim.assign_row(home, A, REPO, "MRB", "#4193", now=time.time())
    assert status == "ok", msg
    assert gitclaim.seat_open_job(home, A)  # now holds/offers 4193


def test_seat_open_job_voids_hold_when_row_offered_to_other(home: Path):
    """Defensive: hold for a job now pinned to another seat does not block."""
    row = _row("MRB", 1858, offered_to=B, offered_ts=_ts(10), offered_count=2)
    _queue(home, [row])
    gitclaim.note_seat_hold(
        home,
        A,
        {"repo": REPO, "task": "MRB", "id": "#1858", "offered_ts": _ts(200)},
    )
    assert gitclaim.seat_open_job(home, A) == ""
    # Hold entry should be dropped when detected void.
    holds = gitclaim._load_seat_holds_unlocked(home)
    assert gitclaim._seat_key(A) not in holds
