"""FR #7906: a fresh ear post sets online. A late QUIT does not clear it."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import bobreport
import registered_machines as rm


def _home(tmp_path):
    os.environ.pop("BOB_DIGEST_HOME", None)
    rm.sync_from_chanserv(
        tmp_path, ["#bobiverse", "#marchhare", "#redqueen", "#flamingo"]
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    return tmp_path


def _iso(when: datetime) -> str:
    return when.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ent(home, mid):
    return bobreport.load_digest(home)["machines"][mid]


def test_late_quit_then_heartbeat_ends_online(tmp_path):
    home = _home(tmp_path)
    assert bobreport.apply_join(home, "bob-marchhare", "#bobiverse").ok
    assert _ent(home, "marchhare")["online"] is True
    out = bobreport.apply_quit(home, "bob-marchhare", event_at="2020-01-01T00:00:00Z")
    assert out.ok and not out.shop_closed
    assert _ent(home, "marchhare")["online"] is True
    doc = bobreport.load_digest(home)
    bobreport._apply_merge_payload(
        doc, "marchhare", {"lastSeen": _iso(datetime.now(timezone.utc))}
    )
    bobreport.save_digest(home, doc)
    ent = _ent(home, "marchhare")
    assert ent["online"] is True
    assert ent["status"] == "I am online"


def test_heartbeat_without_join_marks_online(tmp_path):
    home = _home(tmp_path)
    doc = bobreport.load_digest(home)
    bobreport._apply_merge_payload(
        doc, "marchhare", {"lastSeen": _iso(datetime.now(timezone.utc))}
    )
    bobreport.save_digest(home, doc)
    ent = _ent(home, "marchhare")
    assert ent["online"] is True
    assert ent["status"] == "I am online"


def test_quiet_longer_than_window_marks_offline(tmp_path):
    home = _home(tmp_path)
    doc = bobreport.load_digest(home)
    ent = bobreport._machine_entry(doc, "marchhare")
    ent["online"] = True
    ent["status"] = "I am online"
    ent["lastSeen"] = _iso(datetime.now(timezone.utc) - timedelta(seconds=181))
    bobreport.save_digest(home, doc)
    doc = bobreport.load_digest(home)
    ent = doc["machines"]["marchhare"]
    assert bobreport.apply_ear_publish_staleness(ent, report=False) is True
    assert ent["online"] is False
    assert ent["status"] == "I am offline"


def test_stale_last_seen_does_not_mark_online(tmp_path):
    home = _home(tmp_path)
    bobreport.shop_down(home, "marchhare")
    doc = bobreport.load_digest(home)
    bobreport._apply_merge_payload(
        doc,
        "marchhare",
        {"lastSeen": _iso(datetime.now(timezone.utc) - timedelta(seconds=181))},
    )
    bobreport.save_digest(home, doc)
    assert _ent(home, "marchhare")["online"] is False


def test_quit_without_fresh_presence_still_marks_redqueen_and_flamingo_offline(tmp_path):
    home = _home(tmp_path)
    for nick, mid in (("bob-redqueen", "redqueen"), ("bob-flamingo", "flamingo")):
        bobreport.apply_join(home, nick, "#bobiverse")
        doc = bobreport.load_digest(home)
        ent = doc["machines"][mid]
        ent.pop("presence_at", None)
        ent.pop("lastSeen", None)
        bobreport.save_digest(home, doc)
        out = bobreport.apply_quit(home, nick)
        assert out.shop_closed is True
        assert _ent(home, mid)["online"] is False
        assert _ent(home, mid)["status"] == "I am offline"


def test_stuck_offline_with_fresh_seen_reports_once(tmp_path, monkeypatch):
    filed = []

    def _capture(machine_id):
        filed.append(machine_id)

    monkeypatch.setattr(bobreport, "report_digest_online_stuck", _capture)
    home = _home(tmp_path)
    bobreport.shop_down(home, "marchhare")
    doc = bobreport.load_digest(home)
    ent = doc["machines"]["marchhare"]
    ent["offline_at"] = _iso(datetime.now(timezone.utc) - timedelta(seconds=181))
    ent["online_stuck_reported"] = False
    bobreport._apply_merge_payload(
        doc, "marchhare", {"lastSeen": _iso(datetime.now(timezone.utc))}
    )
    bobreport.save_digest(home, doc)
    assert filed == ["marchhare"]
    assert _ent(home, "marchhare")["online"] is True
    doc = bobreport.load_digest(home)
    doc["machines"]["marchhare"]["online"] = False
    doc["machines"]["marchhare"]["offline_at"] = _iso(
        datetime.now(timezone.utc) - timedelta(seconds=181)
    )
    bobreport._apply_merge_payload(
        doc, "marchhare", {"lastSeen": _iso(datetime.now(timezone.utc))}
    )
    assert filed == ["marchhare"]
