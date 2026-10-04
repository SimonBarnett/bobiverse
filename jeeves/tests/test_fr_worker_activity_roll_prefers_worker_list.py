"""Peer merge must not blank worker_list-driven digest activity.

When seats ACK via worker-work, activity lives in worker_list + working_on.
Legacy pid-keyed workers often get empty working_on on pcent/merge heartbeats;
_roll_working_on used to clear machine working_on and leave the public digest
looking idle while export workers still showed doing.
"""
from __future__ import annotations

from pathlib import Path

import bobreport


MID = "win-mpre8vi4u6u"
NICK = f"{MID}-15656"
PID = "15656"


def _roster(home: Path) -> None:
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["win-mpre8vi4u6u","marchhare"]}',
        encoding="utf-8",
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None


def _seed(home: Path) -> None:
    _roster(home)
    doc = bobreport.load_digest(home)
    ent = bobreport._machine_entry(doc, MID)
    ent["online"] = True
    ent["worker_list"] = [
        {
            "nick": NICK,
            "state": "doing",
            "work": "bobiverse MRB #1477",
            "updated": "2026-10-04T07:41:56Z",
        }
    ]
    ent["workers"] = {
        PID: bobreport._coerce_worker(
            MID,
            PID,
            {
                "state": "idle",
                "working_on": "",
                "nick": NICK,
            },
        )
    }
    bobreport._refresh_machine_activity_from_worker_list(ent)
    bobreport.save_digest(home, doc)


def test_roll_working_on_falls_back_to_worker_list(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _seed(tmp_path)
    doc = bobreport.load_digest(tmp_path)
    ent = bobreport._machine_entry(doc, MID)
    assert ent.get("working_on") == "bobiverse MRB #1477"
    # Simulate merge heartbeat: legacy pid row idle/empty, then roll.
    ent["workers"][PID]["state"] = "idle"
    ent["workers"][PID]["working_on"] = ""
    bobreport._roll_working_on(ent)
    assert ent.get("working_on") == "bobiverse MRB #1477"


def test_merge_heartbeat_preserves_worker_list_activity(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _seed(tmp_path)
    out = bobreport.apply_callback(
        tmp_path,
        {
            "op": "merge",
            "machine": MID,
            "pid": int(PID),
            "state": "running",
            "pcent": {"cursor-models": 42},
        },
        briefer_nick="Jeeves",
    )
    assert out.ok, out.err
    doc = bobreport.load_digest(tmp_path)
    ent = (doc.get("machines") or {}).get(MID) or {}
    assert ent.get("working_on") == "bobiverse MRB #1477"
    exported = bobreport.build_digest_object(tmp_path, "Jeeves")["machines"][MID]
    assert exported.get("working_on") == "bobiverse MRB #1477"
    rows = exported.get("workers") or []
    assert any(
        r.get("nick") == NICK and r.get("state") == "doing" and "1477" in (r.get("work") or "")
        for r in rows
    )


def test_worker_work_mirrors_legacy_workers(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _roster(tmp_path)
    out = bobreport.apply_callback(
        tmp_path,
        {
            "op": "worker-work",
            "machine": MID,
            "nick": NICK,
            "state": "doing",
            "work": "bobiverse FR #1500",
        },
        briefer_nick="Jeeves",
    )
    assert out.ok, out.err
    doc = bobreport.load_digest(tmp_path)
    ent = (doc.get("machines") or {}).get(MID) or {}
    assert ent.get("working_on") == "bobiverse FR #1500"
    legacy = (ent.get("workers") or {}).get(PID) or {}
    assert legacy.get("working_on") == "bobiverse FR #1500"
    assert str(legacy.get("state") or "").lower() in ("running", "doing")
