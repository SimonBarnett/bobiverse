"""Hostile MRB #1495: roll blank when worker_list idle; remove clears legacy mirror."""
from __future__ import annotations

from pathlib import Path

import bobreport

MID = "win-mpre8vi4u6u"
NICK = f"{MID}-15656"
PID = "15656"


def _roster(home: Path) -> None:
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["win-mpre8vi4u6u"]}',
        encoding="utf-8",
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None


def test_roll_blanks_when_worker_list_also_idle(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _roster(tmp_path)
    doc = bobreport.load_digest(tmp_path)
    ent = bobreport._machine_entry(doc, MID)
    ent["working_on"] = "stale leftover"
    ent["worker_list"] = [
        {"nick": NICK, "state": "idle", "work": "", "updated": "2026-10-04T08:00:00Z"}
    ]
    ent["workers"] = {
        PID: bobreport._coerce_worker(MID, PID, {"state": "idle", "working_on": "", "nick": NICK})
    }
    bobreport._roll_working_on(ent)
    assert ent.get("working_on") in ("", None)


def test_worker_remove_clears_legacy_mirror(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _roster(tmp_path)
    assert bobreport.apply_callback(
        tmp_path,
        {"op": "worker-work", "machine": MID, "nick": NICK, "state": "doing", "work": "bobiverse FR #1"},
        briefer_nick="Jeeves",
    ).ok
    assert bobreport.apply_callback(
        tmp_path,
        {"op": "worker-remove", "machine": MID, "nick": NICK},
        briefer_nick="Jeeves",
    ).ok
    doc = bobreport.load_digest(tmp_path)
    ent = (doc.get("machines") or {}).get(MID) or {}
    assert PID not in (ent.get("workers") or {})
