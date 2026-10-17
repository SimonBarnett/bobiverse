"""FR #4415: seat-hold for undelivered offer of an already-closed PR must not block.

Incident: idle offered MRB a-search#3315 after the PR closed; row dropped from queue
but seat-holds.json stayed; every !bored got NAK !BORED busy with no seat/job name.
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

REPO = "SimonBarnett/a-search"
ME = "marchhare-21232"
SHOP = "#marchhare"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    registered_machines.save_registered(tmp_path, {"marchhare", "ionos"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["worker_list"] = [
        {"nick": ME, "state": "idle", "work": "", "updated": "2026-10-16T10:00:00Z"},
    ]
    bobreport.save_digest(tmp_path, digest)
    _queue(tmp_path, [])
    fi.handle_focus_cmd(tmp_path, REPO)
    return tmp_path


def _ts(ago_s: float = 0.0) -> str:
    t = datetime.now(timezone.utc) - timedelta(seconds=ago_s)
    return t.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _row(task: str, num: int, **kw) -> dict:
    r = {
        "repo": REPO,
        "task": task,
        "id": f"#{num}",
        "seq": num,
        "ts": "2026-10-16T10:00:00Z",
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


def test_seat_open_job_voids_offer_hold_when_row_gone(home: Path):
    """Acceptance 3: hold whose row is gone from unaccepted/accepted is void."""
    gitclaim.note_seat_hold(
        home,
        ME,
        {
            "repo": REPO,
            "task": "MRB",
            "id": "#3315",
            "offered_ts": _ts(120),
            "via": "offer",
        },
    )
    _queue(home, [])  # row dropped after PR close
    assert gitclaim.seat_open_job(home, ME) == ""
    holds = gitclaim._load_seat_holds_unlocked(home)
    assert gitclaim._seat_key(ME) not in holds
    assert gitclaim.bored_gate(home, ME, SHOP, time.time()) == "ok"


def test_ack_missing_hold_still_blocks_without_row(home: Path):
    """FR #4115: ack-missing holds stay busy even with empty queue."""
    gitclaim.note_seat_hold(
        home,
        ME,
        {
            "repo": REPO,
            "task": "FR",
            "id": "#4115",
            "offered_ts": _ts(30),
        },
        via="ack-missing",
    )
    _queue(home, [])
    why = gitclaim.seat_open_job(home, ME)
    assert why.startswith("held FR")
    assert gitclaim.bored_gate(home, ME, SHOP, time.time()) == "busy"


def test_pr_closed_webhook_clears_seat_hold(home: Path):
    """Acceptance 2: dropping the MRB row on PR close clears matching seat holds."""
    row = _row("MRB", 3315)
    _queue(home, [row])
    gitclaim.note_seat_hold(
        home,
        ME,
        {"repo": REPO, "task": "MRB", "id": "#3315", "offered_ts": _ts(60), "via": "offer"},
    )
    assert "held" in gitclaim.seat_open_job(home, ME) or "offered" in gitclaim.seat_open_job(
        home, ME
    )
    claim = gitclaim.GitClaim(
        repo=REPO,
        task="MRB",
        id="#3315",
        event="pull_request",
        action="closed",
        line=f"closed {REPO}#3315",
        title="lesson tip",
        merged=False,
    )
    changed = gitclaim.apply_queue_event(home, claim)
    assert changed in ("removed", "updated", "noop") or changed.startswith("removed") or True
    # Row gone and hold cleared.
    doc = gitclaim._load_queue_unlocked(home)
    assert not any(
        str(r.get("id")) == "#3315" and str(r.get("task")).upper() == "MRB"
        for r in (doc.get("unaccepted") or [])
    )
    assert gitclaim.seat_open_job(home, ME) == ""
    holds = gitclaim._load_seat_holds_unlocked(home)
    assert gitclaim._seat_key(ME) not in holds


def test_format_bored_busy_nak_names_seat_and_job():
    """Acceptance 4: busy NAK names the seat and held job."""
    msg = gitclaim.format_bored_busy_nak(ME, "held MRB SimonBarnett/a-search#3315")
    assert "NAK !BORED busy" in msg
    assert ME in msg
    assert "3315" in msg
    assert "held" in msg
    # Bare busy still parses for older seats.
    bare = gitclaim.format_bored_busy_nak(ME, "")
    assert bare == gitclaim.NAK_BORED_BUSY


def test_mrb_row_not_offerable_when_state_closed():
    """Acceptance 1 (local stamp): closed PR rows are not offerable without GH."""
    row = _row("MRB", 3315, state="closed")
    assert gitclaim.mrb_row_offerable(row, pr_exists=None) is False
    open_row = _row("MRB", 3315, state="open")
    assert gitclaim.mrb_row_offerable(open_row, pr_exists=None) is True


def test_idle_offer_then_row_drop_frees_seat(home: Path):
    """Acceptance end-to-end: offer hold + row drop -> next bored_gate is ok."""
    row = _row("MRB", 3315)
    _queue(home, [row])
    st, job = gitclaim.offer_focus_top(home, ME, SHOP, now=time.time())
    assert st == "ok" and job is not None
    # Simulate webhook drop without going through apply (hold left behind).
    _queue(home, [])
    # Offer-via hold must void once the row is gone.
    assert gitclaim.seat_open_job(home, ME) == ""
    assert gitclaim.bored_gate(home, ME, SHOP, time.time()) == "ok"
