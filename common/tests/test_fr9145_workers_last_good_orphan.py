"""FR #9145: delete-worker / worker-remove clear last-good; TTL suppresses stale export."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bobcallback
import bobreport
import intake
import registered_machines as rm

ALLOW = {"127.0.0.1"}
MID = "redqueen"
NICK = "redqueen-1824"
PID = "1824"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _home(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    rm.sync_from_chanserv(tmp_path, ["#bobiverse", f"#{MID}", "#marchhare"])
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    bobreport.reset_dedupe()
    return tmp_path


def post(home, obj, *, rate=None, headers=None):
    return bobcallback.handle_request(
        "POST",
        "/bob/v1/report",
        headers or {"Content-Type": "application/json"},
        json.dumps(obj).encode(),
        "127.0.0.1",
        home,
        ALLOW,
        filer=intake.FakeGitHubFiler(),
        report_rate=rate,
    )


def _incident_ent(ent: dict, *, at: str | None = None) -> None:
    ent["online"] = True
    ent["workers"] = {}
    ent["worker_list"] = []
    ent["workers_last_good"] = [
        {"nick": NICK, "state": "out_of_fuel", "work": "out-of-fuel", "updated": at or "2026-11-21T12:00:00Z"}
    ]
    ent["workers_last_good_at"] = at or "2026-11-21T12:00:00Z"
    ent["workers_stale"] = True


def test_worker_remove_incident_fixture_clears_last_good_and_stale(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    doc = bobreport.load_digest(home)
    ent = bobreport._machine_entry(doc, MID)
    _incident_ent(ent, at=_iso(datetime.now(timezone.utc)))
    bobreport.save_digest(home, doc)
    exported = bobreport.export_machine_for_tray(home, MID, ent)
    assert NICK in {w["nick"] for w in (exported.get("workers") or [])}

    code, _body = post(home, {"op": "worker-remove", "machine": MID, "nick": NICK})
    assert code == 204
    ent2 = bobreport.load_digest(home)["machines"][MID]
    assert not ent2.get("workers_last_good")
    assert not ent2.get("workers_stale")
    exported2 = bobreport.export_machine_for_tray(home, MID, ent2)
    assert exported2.get("workers") == []
    assert not exported2.get("workers_stale")


def test_delete_worker_incident_fixture_clears_last_good(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    doc = bobreport.load_digest(home)
    ent = bobreport._machine_entry(doc, MID)
    _incident_ent(ent, at=_iso(datetime.now(timezone.utc)))
    bobreport.save_digest(home, doc)

    code, _body = post(home, {"op": "delete-worker", "machine": MID, "pid": int(PID)})
    assert code == 204
    ent2 = bobreport.load_digest(home)["machines"][MID]
    assert not ent2.get("workers_last_good")
    assert not ent2.get("workers_stale")
    assert bobreport.export_machine_for_tray(home, MID, ent2).get("workers") == []


def test_delete_worker_absent_is_200_then_merge_repeat_delete(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    code, _ = post(home, {"op": "delete-worker", "machine": MID, "pid": 99999})
    assert code == 200
    # Fresh upsert then delete of a live pid still works (dedupe not poisoned by absent delete).
    assert post(home, {"op": "worker-upsert", "machine": MID, "nick": "redqueen-99999", "state": "idle"})[0] == 204
    doc = bobreport.load_digest(home)
    ent = doc["machines"][MID]
    # Mirror legacy map entry for delete-worker path.
    ent.setdefault("workers", {})["99999"] = {"nick": "redqueen-99999", "state": "idle"}
    bobreport.save_digest(home, doc)
    bobreport.reset_dedupe()
    assert post(home, {"op": "delete-worker", "machine": MID, "pid": 99999})[0] == 204
    # Repeat delete is unchanged.
    assert post(home, {"op": "delete-worker", "machine": MID, "pid": 99999})[0] == 200


def test_delete_worker_leaves_other_machine_snapshot(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    doc = bobreport.load_digest(home)
    ent = bobreport._machine_entry(doc, MID)
    now = _iso(datetime.now(timezone.utc))
    ent["online"] = True
    ent["worker_list"] = []
    ent["workers"] = {}
    ent["workers_last_good"] = [
        {"nick": NICK, "state": "idle", "work": "", "updated": now},
        {"nick": "marchhare-1824", "state": "idle", "work": "", "updated": now},
    ]
    ent["workers_last_good_at"] = now
    ent["workers_stale"] = True
    bobreport.save_digest(home, doc)

    assert post(home, {"op": "delete-worker", "machine": MID, "pid": int(PID)})[0] == 204
    ent2 = bobreport.load_digest(home)["machines"][MID]
    nicks = {r["nick"] for r in (ent2.get("workers_last_good") or [])}
    assert NICK not in nicks
    assert "marchhare-1824" in nicks
    assert ent2.get("workers_stale") is True


def test_delete_worker_legacy_short_nick_leading_zero_pid(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    mid = "marchhare"
    doc = bobreport.load_digest(home)
    ent = bobreport._machine_entry(doc, mid)
    now = _iso(datetime.now(timezone.utc))
    ent["online"] = True
    ent["worker_list"] = []
    ent["workers"] = {}
    ent["workers_last_good"] = [
        {"nick": "w-mh-01824", "state": "out_of_fuel", "work": "out-of-fuel", "updated": now}
    ]
    ent["workers_last_good_at"] = now
    ent["workers_stale"] = True
    bobreport.save_digest(home, doc)

    assert post(home, {"op": "delete-worker", "machine": mid, "pid": 1824})[0] == 204
    ent2 = bobreport.load_digest(home)["machines"][mid]
    assert not ent2.get("workers_last_good")
    assert not ent2.get("workers_stale")


def test_ttl_suppresses_expired_fallback_export(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    monkeypatch.setenv("BOB_DIGEST_LAST_GOOD_MAX_S", "1800")
    doc = bobreport.load_digest(home)
    ent = bobreport._machine_entry(doc, MID)
    old = _iso(datetime.now(timezone.utc) - timedelta(seconds=3600))
    _incident_ent(ent, at=old)
    bobreport.save_digest(home, doc)
    exported = bobreport.export_machine_for_tray(home, MID, ent)
    assert exported.get("workers") == []
    assert not exported.get("workers_stale")


def test_ttl_unknown_timestamp_treated_expired(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    doc = bobreport.load_digest(home)
    ent = bobreport._machine_entry(doc, MID)
    ent["online"] = True
    ent["worker_list"] = []
    ent["workers"] = {}
    ent["workers_last_good"] = [
        {"nick": NICK, "state": "idle", "work": "", "updated": "2026-11-21T12:00:00Z"}
    ]
    ent.pop("workers_last_good_at", None)
    ent["workers_stale"] = True
    bobreport.save_digest(home, doc)
    assert bobreport.worker_list_for_export(ent) == []
    assert bobreport._workers_last_good_expired(ent) is True


def test_restore_drops_expired_snapshot(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    monkeypatch.setenv("BOB_DIGEST_LAST_GOOD_MAX_S", "60")
    doc = bobreport.load_digest(home)
    ent = bobreport._machine_entry(doc, MID)
    old = _iso(datetime.now(timezone.utc) - timedelta(seconds=120))
    ent["online"] = True
    ent["worker_list"] = []
    ent["workers_last_good"] = [
        {"nick": NICK, "state": "idle", "work": "", "updated": old}
    ]
    ent["workers_last_good_at"] = old
    assert bobreport._restore_workers_last_good_if_empty(ent) is False
    assert not ent.get("workers_last_good")
    assert not ent.get("workers_stale")
    assert ent.get("worker_list") == []


def test_snapshot_preserves_timestamp_when_already_stale(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    doc = bobreport.load_digest(home)
    ent = bobreport._machine_entry(doc, MID)
    prior = "2026-11-22T10:00:00Z"
    ent["workers_stale"] = True
    ent["workers_last_good_at"] = prior
    ent["worker_list"] = [
        {"nick": NICK, "state": "idle", "work": "", "updated": prior}
    ]
    bobreport._snapshot_workers_last_good(ent)
    assert ent.get("workers_last_good_at") == prior


def test_fresh_upsert_restamps_and_clears_stale(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    doc = bobreport.load_digest(home)
    ent = bobreport._machine_entry(doc, MID)
    prior = "2026-11-22T10:00:00Z"
    ent["workers_stale"] = True
    ent["workers_last_good_at"] = prior
    ent["worker_list"] = [
        {"nick": NICK, "state": "idle", "work": "", "updated": prior}
    ]
    bobreport.save_digest(home, doc)
    assert post(home, {"op": "worker-upsert", "machine": MID, "nick": NICK, "state": "idle"})[0] in (200, 204)
    ent2 = bobreport.load_digest(home)["machines"][MID]
    assert not ent2.get("workers_stale")
    assert ent2.get("workers_last_good_at") != prior


def test_workers_last_good_max_s_config(monkeypatch):
    monkeypatch.delenv("BOB_DIGEST_LAST_GOOD_MAX_S", raising=False)
    assert bobreport.workers_last_good_max_s() == 1800.0
    monkeypatch.setenv("BOB_DIGEST_LAST_GOOD_MAX_S", "30")
    assert bobreport.workers_last_good_max_s() == 60.0
    monkeypatch.setenv("BOB_DIGEST_LAST_GOOD_MAX_S", "bogus")
    assert bobreport.workers_last_good_max_s() == 1800.0
    monkeypatch.setenv("BOB_DIGEST_LAST_GOOD_MAX_S", "900")
    assert bobreport.workers_last_good_max_s() == 900.0


def test_expired_stale_restored_list_exports_empty(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    monkeypatch.setenv("BOB_DIGEST_LAST_GOOD_MAX_S", "1800")
    doc = bobreport.load_digest(home)
    ent = bobreport._machine_entry(doc, MID)
    old = _iso(datetime.now(timezone.utc) - timedelta(seconds=4000))
    ent["online"] = True
    ent["workers_stale"] = True
    ent["workers_last_good_at"] = old
    ent["workers_last_good"] = [
        {"nick": NICK, "state": "idle", "work": "", "updated": old}
    ]
    ent["worker_list"] = list(ent["workers_last_good"])
    exported = bobreport.export_machine_for_tray(home, MID, ent)
    assert exported.get("workers") == []
    assert not exported.get("workers_stale")
