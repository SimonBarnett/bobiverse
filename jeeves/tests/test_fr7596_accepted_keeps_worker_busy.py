"""FR #7596: accepted ACK keeps worker_list busy across an idle heartbeat.

While a seat holds an accepted job (ACK .. DONE/GIVEUP), digest worker_list must
stay doing with running>=1 and the job listed. An idle heartbeat (kind/model
POST) must not blank it. After accepted is cleared, idle may apply.
Generic host ids only.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import bobreport
import gitclaim
import registered_machines as rm

MID = "boxa"
SEAT = "boxa-100"
WORK = "bobiverse MRB #7581"


def _roster(home: Path) -> None:
    rm.sync_from_chanserv(home, ["#bobiverse", f"#{MID}"])
    bobreport._SEAT_ROSTER_CACHE["key"] = None


def _write_accepted(home: Path, *, nick: str = SEAT, issue: str = "#7581") -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "MRB",
                    "id": issue,
                    "nick": nick,
                    "accepted_by": nick,
                    "accepted_ts": "2026-11-15T17:50:00Z",
                    "ts": "2026-11-15T17:40:00Z",
                    "line": "x",
                }
            ],
            "done": [],
        },
    )


def _write_empty_accepted(home: Path) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [], "done": []},
    )


def _worker_row(home: Path) -> dict:
    doc = bobreport.load_digest(home)
    ent = (doc.get("machines") or {}).get(MID) or {}
    rows = bobreport._coerce_worker_list(ent.get("worker_list"))
    for row in rows:
        if str(row.get("nick") or "").lower() == SEAT.lower():
            return row
    return {}


def test_fr7596_idle_heartbeat_keeps_accepted_mrb_busy(tmp_path, monkeypatch):
    home = tmp_path / "digest"
    home.mkdir()
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    _roster(home)
    _write_accepted(home)

    out_ack = bobreport.apply_callback(
        home,
        {
            "op": "worker-work",
            "machine": MID,
            "nick": SEAT,
            "state": "doing",
            "work": WORK,
        },
        briefer_nick="Jeeves",
    )
    assert out_ack.ok

    # Heartbeat shaped like post_digest_seat_kind (state defaults to idle).
    out_hb = bobreport.apply_callback(
        home,
        {
            "op": "worker-work",
            "machine": MID,
            "nick": SEAT,
            "state": "idle",
            "kind": "grok",
            "start_model": "grok-4",
        },
        briefer_nick="Jeeves",
    )
    assert out_hb.ok

    row = _worker_row(home)
    assert row.get("state") == "doing"
    assert "7581" in str(row.get("work") or "")
    assert "MRB" in str(row.get("work") or "").upper()

    ent = bobreport.load_digest(home)["machines"][MID]
    bobreport._refresh_machine_activity_from_worker_list(ent)
    assert int(ent.get("running") or 0) >= 1
    jobs = ent.get("jobs") or []
    assert any(str(j.get("nick") or "").lower() == SEAT for j in jobs)
    assert any(
        str(j.get("issue") or "") == "7581"
        or "7581" in str(j.get("description") or "")
        for j in jobs
    )

    exported = bobreport.export_machine_for_tray(
        home,
        MID,
        ent,
        now=datetime(2026, 11, 15, 17, 54, 12, tzinfo=timezone.utc),
    )
    assert int(exported.get("running") or 0) >= 1
    assert any(
        str(j.get("issue") or "") == "7581"
        or "7581" in str(j.get("description") or "")
        for j in (exported.get("jobs") or [])
    )


def test_fr7596_idle_after_accepted_cleared_goes_idle(tmp_path, monkeypatch):
    home = tmp_path / "digest"
    home.mkdir()
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    _roster(home)
    _write_accepted(home)

    bobreport.apply_callback(
        home,
        {
            "op": "worker-work",
            "machine": MID,
            "nick": SEAT,
            "state": "doing",
            "work": WORK,
        },
    )
    _write_empty_accepted(home)

    out = bobreport.apply_callback(
        home,
        {
            "op": "worker-work",
            "machine": MID,
            "nick": SEAT,
            "state": "idle",
        },
    )
    assert out.ok
    row = _worker_row(home)
    assert row.get("state") == "idle"
    assert not (row.get("work") or "").strip()

    ent = bobreport.load_digest(home)["machines"][MID]
    bobreport._refresh_machine_activity_from_worker_list(ent)
    assert int(ent.get("running") or 0) == 0
    assert (ent.get("jobs") or []) == []


def test_fr7596_source_has_no_banned_machine_names():
    root = Path(__file__).resolve().parents[2]
    src = (root / "common" / "scripts" / "bobreport.py").read_text(encoding="utf-8")
    start = src.index("def accepted_work_for_nick")
    end = src.index("\ndef _apply_worker_op", start)
    chunk = (src[start:end] + Path(__file__).read_text(encoding="utf-8")).lower()
    banned = ("wal" + "rus", "red" + "queen", "ion" + "os", "flam" + "ingo")
    for name in banned:
        assert name not in chunk
