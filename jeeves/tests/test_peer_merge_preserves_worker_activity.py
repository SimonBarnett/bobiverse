"""Empty peer merge working_on must not wipe chair worker-work activity."""
from __future__ import annotations

from pathlib import Path

import bobreport

MID = "win-mpre8vi4u6u"
NICK = f"{MID}-20596"
PID = "20596"


def _roster(home: Path) -> None:
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["win-mpre8vi4u6u"]}',
        encoding="utf-8",
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None


def test_empty_peer_merge_keeps_worker_list_activity(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _roster(tmp_path)
    assert bobreport.apply_callback(
        tmp_path,
        {
            "op": "worker-work",
            "machine": MID,
            "nick": NICK,
            "state": "doing",
            "work": "bobiverse MRB #1538",
        },
        briefer_nick="Jeeves",
    ).ok
    doc = bobreport.load_digest(tmp_path)
    ent = (doc.get("machines") or {}).get(MID) or {}
    assert ent.get("working_on") == "bobiverse MRB #1538"

    # Peer heartbeat with blank working_on and no pid (common tray merge).
    assert bobreport.apply_callback(
        tmp_path,
        {"op": "merge", "machine": MID, "online": True, "working_on": "", "weekly": 53},
        briefer_nick="bob-win-mpre8vi4u6u",
    ).ok
    doc2 = bobreport.load_digest(tmp_path)
    ent2 = (doc2.get("machines") or {}).get(MID) or {}
    assert ent2.get("working_on") == "bobiverse MRB #1538"
    rows = bobreport.worker_list_for_export(ent2)
    assert any(r.get("nick") == NICK and r.get("state") == "doing" for r in rows)


def test_export_refreshes_working_on_from_worker_list(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _roster(tmp_path)
    doc = bobreport.load_digest(tmp_path)
    ent = bobreport._machine_entry(doc, MID)
    ent["online"] = True
    ent["working_on"] = ""  # peer-blanked
    ent["worker_list"] = [
        {
            "nick": NICK,
            "state": "doing",
            "work": "bobiverse FR #1520",
            "updated": "2026-10-04T10:00:00Z",
        }
    ]
    bobreport.save_digest(tmp_path, doc)
    exported = bobreport.export_machine_for_tray(tmp_path, MID, ent)
    assert exported.get("working_on") == "bobiverse FR #1520"
    assert any(w.get("nick") == NICK for w in (exported.get("workers") or []))
