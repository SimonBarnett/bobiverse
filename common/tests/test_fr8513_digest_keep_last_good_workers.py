"""FR #8513: shop-down / ear churn must not leave online+workers=[] permanently."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import bobreport
import registered_machines as rm

MID = "redqueen"
NICK_A = "redqueen-9192"
NICK_B = "redqueen-9868"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _home(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    rm.sync_from_chanserv(tmp_path, ["#bobiverse", f"#{MID}"])
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    return tmp_path


def _upsert(home: Path, nick: str, *, state: str = "idle", work: str = "") -> None:
    payload = {"op": "worker-upsert", "machine": MID, "nick": nick, "state": state}
    if work:
        payload["work"] = work
        payload["op"] = "worker-work"
    assert bobreport.apply_callback(home, payload, briefer_nick="Jeeves").ok


def test_shop_down_keeps_last_good_and_restore_on_online(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _upsert(home, NICK_A, state="idle")
    _upsert(home, NICK_B, state="doing", work="bobiverse MRB #8487")
    doc = bobreport.load_digest(home)
    ent = doc["machines"][MID]
    assert len(bobreport._coerce_worker_list(ent.get("worker_list"))) == 2

    bobreport.shop_down(home, MID)
    ent = bobreport.load_digest(home)["machines"][MID]
    assert ent.get("online") is False
    assert bobreport._coerce_worker_list(ent.get("worker_list")) == []
    last = bobreport._coerce_worker_list(ent.get("workers_last_good"))
    assert {r["nick"] for r in last} == {NICK_A, NICK_B}
    # Offline export must stay empty (shop is down).
    exported_off = bobreport.export_machine_for_tray(home, MID, ent)
    assert exported_off.get("workers") == []

    # Fresh heartbeat brings the machine online and restores last-good.
    doc = bobreport.load_digest(home)
    bobreport._apply_merge_payload(
        doc, MID, {"lastSeen": _iso(datetime.now(timezone.utc)), "online": True}
    )
    bobreport.save_digest(home, doc)
    ent2 = bobreport.load_digest(home)["machines"][MID]
    assert ent2.get("online") is True
    rows = bobreport._coerce_worker_list(ent2.get("worker_list"))
    assert {r["nick"] for r in rows} == {NICK_A, NICK_B}
    assert ent2.get("workers_stale") is True
    exported = bobreport.export_machine_for_tray(home, MID, ent2)
    assert {w["nick"] for w in (exported.get("workers") or [])} == {NICK_A, NICK_B}
    assert exported.get("workers_stale") is True


def test_online_empty_worker_list_exports_last_good(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _upsert(home, NICK_A)
    bobreport.shop_down(home, MID)
    doc = bobreport.load_digest(home)
    ent = doc["machines"][MID]
    # Simulate ear back online without restore path (sticky empty list).
    ent["online"] = True
    ent["status"] = "I am online"
    ent["worker_list"] = []
    ent.pop("offline_at", None)
    bobreport.save_digest(home, doc)
    exported = bobreport.export_machine_for_tray(home, MID, ent)
    assert any(w.get("nick") == NICK_A for w in (exported.get("workers") or []))
    assert exported.get("workers_stale") is True


def test_digest_post_failed_merge_marks_stale(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _upsert(home, NICK_A)
    doc = bobreport.load_digest(home)
    bobreport._apply_merge_payload(
        doc,
        MID,
        {
            "online": True,
            "pid": 9192,
            "nick": NICK_A,
            "state": "unhealthy",
            "kind": "grok",
            "digest_post_failed": True,
        },
    )
    bobreport.save_digest(home, doc)
    ent = bobreport.load_digest(home)["machines"][MID]
    assert ent.get("digest_post_failed") is True
    assert ent.get("workers_stale") is True
    exported = bobreport.export_machine_for_tray(home, MID, ent)
    assert exported.get("digest_post_failed") is True or exported.get("workers_stale") is True
    assert any(w.get("nick") == NICK_A for w in (exported.get("workers") or []))


def test_fresh_upsert_clears_stale(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _upsert(home, NICK_A)
    bobreport.shop_down(home, MID)
    doc = bobreport.load_digest(home)
    bobreport._set_online(doc["machines"][MID], True)
    bobreport.save_digest(home, doc)
    assert bobreport.load_digest(home)["machines"][MID].get("workers_stale") is True
    _upsert(home, NICK_A, state="idle")
    ent = bobreport.load_digest(home)["machines"][MID]
    assert not ent.get("workers_stale")
    assert not ent.get("digest_post_failed")
    exported = bobreport.export_machine_for_tray(home, MID, ent)
    assert not exported.get("workers_stale")


def test_apply_join_restores_last_good(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _upsert(home, NICK_B, state="doing", work="bobiverse FR #8513")
    bobreport.shop_down(home, MID)
    out = bobreport.apply_join(home, "Bob-redqueen", "#bobiverse")
    assert out.ok
    ent = bobreport.load_digest(home)["machines"][MID]
    assert ent.get("online") is True
    rows = bobreport._coerce_worker_list(ent.get("worker_list"))
    assert any(r.get("nick") == NICK_B for r in rows)
    assert ent.get("workers_stale") is True
