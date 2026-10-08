"""FR #3450: hours webhook create, idempotency, filters, auto-close, de-overlap, credentials."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bobhours
import intake
from bobcallback import handle_request


def _create_body(**kwargs):
    base = {
        "idempotency_key": "k1",
        "agent": "Haitch",
        "on_behalf_of": "SimonB",
        "start": "2026-10-08T09:00:00+01:00",
        "customer": "ce-priority",
        "project": "dayworks",
        "repo_url": "https://github.com/SimonBarnett/ce-priority",
        "description": "Draft Day Works hours",
        "source": "marchhare",
    }
    base.update(kwargs)
    return base


def test_create_open_and_closed(tmp_path: Path):
    code, entry = bobhours.create_entry(tmp_path, _create_body())
    assert code == 201
    assert entry["status"] == "open"
    assert entry["end"] is None
    assert entry["id"].startswith("h_")

    code2, closed = bobhours.create_entry(
        tmp_path,
        _create_body(
            idempotency_key="k2",
            end="2026-10-08T10:30:00+01:00",
        ),
    )
    assert code2 == 201
    assert closed["status"] == "closed"
    assert closed["duration_minutes"] == 90


def test_idempotent_retry(tmp_path: Path):
    code1, e1 = bobhours.create_entry(tmp_path, _create_body(idempotency_key="same"))
    code2, e2 = bobhours.create_entry(tmp_path, _create_body(idempotency_key="same"))
    assert code1 == 201
    assert code2 == 200
    assert e1["id"] == e2["id"]
    assert len(list((tmp_path / "hours" / "entries").glob("*.json"))) == 1


def test_filters_by_user_and_london_day(tmp_path: Path):
    bobhours.create_entry(
        tmp_path,
        _create_body(
            idempotency_key="a",
            start="2026-10-08T09:00:00+01:00",
            end="2026-10-08T10:00:00+01:00",
        ),
    )
    bobhours.create_entry(
        tmp_path,
        _create_body(
            idempotency_key="b",
            on_behalf_of="Other",
            start="2026-10-08T11:00:00+01:00",
            end="2026-10-08T12:00:00+01:00",
        ),
    )
    bobhours.create_entry(
        tmp_path,
        _create_body(
            idempotency_key="c",
            start="2026-10-09T09:00:00+01:00",
            end="2026-10-09T10:00:00+01:00",
        ),
    )
    from datetime import date

    got = bobhours.filter_entries(
        bobhours.list_entries(tmp_path),
        user="SimonB",
        day_from=date(2026, 10, 8),
        day_to=date(2026, 10, 8),
    )
    assert len(got) == 1
    assert got[0]["idempotency_key"] == "a"


def test_timeout_auto_close(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BOB_HOURS_OPEN_TIMEOUT_MIN", "30")
    code, entry = bobhours.create_entry(tmp_path, _create_body(idempotency_key="open1"))
    assert code == 201
    # Backdate heartbeat beyond timeout
    stale = datetime.now(timezone.utc) - timedelta(minutes=90)
    entry["last_heartbeat"] = stale.isoformat().replace("+00:00", "Z")
    entry["start"] = (stale - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    bobhours._write_entry(tmp_path, entry)

    loaded = bobhours.load_entry(tmp_path, entry["id"])
    closed = bobhours._maybe_auto_close(tmp_path, loaded)
    assert closed["status"] == "auto_closed"
    assert closed["end"] is not None


def test_deoverlap_and_summary(tmp_path: Path):
    # Two overlapping 60-minute entries for same user → raw 120, de-overlapped 90
    bobhours.create_entry(
        tmp_path,
        _create_body(
            idempotency_key="o1",
            agent="A1",
            start="2026-10-08T09:00:00+01:00",
            end="2026-10-08T10:00:00+01:00",
            wbs="5",
            tickets=["PE-1"],
        ),
    )
    bobhours.create_entry(
        tmp_path,
        _create_body(
            idempotency_key="o2",
            agent="A2",
            start="2026-10-08T09:30:00+01:00",
            end="2026-10-08T10:30:00+01:00",
            wbs="5",
            tickets=["PE-1"],
        ),
    )
    from datetime import date

    summary = bobhours.build_summary(
        bobhours.list_entries(tmp_path),
        user="SimonB",
        day_from=date(2026, 10, 8),
        day_to=date(2026, 10, 8),
    )
    assert len(summary["days"]) == 1
    day = summary["days"][0]
    assert day["raw_minutes"] == 120
    assert day["deoverlapped_minutes"] == 90
    assert len(summary["overlaps"]) == 1
    assert summary["overlaps"][0]["minutes"] == 30


def test_credential_field_rejected(tmp_path: Path):
    code, body = bobhours.create_entry(
        tmp_path, _create_body(idempotency_key="bad", password="secret")
    )
    assert code == 400
    assert body["error"] == "credential_field_rejected"
    assert bobhours.contains_credential_fields({"nested": {"api_key": "x"}})


def test_heartbeat_close_withdraw_supersedes(tmp_path: Path):
    _, e = bobhours.create_entry(tmp_path, _create_body(idempotency_key="hb"))
    code, hb = bobhours.heartbeat_entry(tmp_path, e["id"], {})
    assert code == 200
    assert hb["last_heartbeat"] >= e["last_heartbeat"]

    code, closed = bobhours.close_entry(
        tmp_path, e["id"], {"end": "2026-10-08T11:00:00+01:00"}
    )
    assert code == 200
    assert closed["status"] == "closed"

    _, e2 = bobhours.create_entry(
        tmp_path,
        _create_body(
            idempotency_key="rep",
            start="2026-10-08T09:00:00+01:00",
            end="2026-10-08T10:00:00+01:00",
            supersedes=closed["id"],
        ),
    )
    old = bobhours.load_entry(tmp_path, closed["id"])
    assert old["status"] == "withdrawn"
    assert e2["supersedes"] == closed["id"]

    code, w = bobhours.withdraw_entry(tmp_path, e2["id"], {})
    assert code == 200
    assert w["status"] == "withdrawn"


def test_export_csv_and_json(tmp_path: Path):
    bobhours.create_entry(
        tmp_path,
        _create_body(
            idempotency_key="ex",
            end="2026-10-08T10:00:00+01:00",
        ),
    )
    entries = bobhours.filter_entries(bobhours.list_entries(tmp_path), user="SimonB")
    ctype, text = bobhours.export_entries(entries, fmt="csv")
    assert ctype.startswith("text/csv")
    assert "idempotency_key" in text
    assert "ex" in text
    ctype2, text2 = bobhours.export_entries(entries, fmt="json")
    assert "application/json" in ctype2
    assert json.loads(text2)["entries"][0]["idempotency_key"] == "ex"


def test_handle_request_hours_routes(tmp_path: Path):
    body = json.dumps(_create_body(idempotency_key="http1")).encode("utf-8")
    code, payload = handle_request(
        "POST",
        "/bob/v1/hours",
        {"Content-Type": "application/json"},
        body,
        "127.0.0.1",
        tmp_path,
        allow_ips={"127.0.0.1"},
        report_rate=intake.RateLimiter(per_min=100),
    )
    assert code == 201
    entry = json.loads(payload)
    eid = entry["id"]

    code, payload = handle_request(
        "POST",
        f"/bob/v1/hours/{eid}/heartbeat",
        {"Content-Type": "application/json"},
        b"{}",
        "127.0.0.1",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    assert code == 200

    code, payload = handle_request(
        "GET",
        "/bob/v1/hours?user=SimonB&from=2026-10-08&to=2026-10-08",
        {},
        b"",
        "127.0.0.1",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    assert code == 200
    assert len(json.loads(payload)["entries"]) == 1

    code, payload = handle_request(
        "GET",
        "/bob/v1/hours/summary?user=SimonB&date=2026-10-08",
        {},
        b"",
        "127.0.0.1",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    assert code == 200
    assert "days" in json.loads(payload)

    code, payload = handle_request(
        "GET",
        "/bob/v1/hours/export?user=SimonB&format=csv",
        {},
        b"",
        "127.0.0.1",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    assert code == 200
    assert b"idempotency_key" in payload


def test_schema_rejects_bad_fields(tmp_path: Path):
    code, body = bobhours.create_entry(tmp_path, _create_body(idempotency_key=""))
    assert code == 400
    assert body["error"] == "bad_idempotency_key"
    code, body = bobhours.create_entry(
        tmp_path, _create_body(idempotency_key="x", start="not-a-date")
    )
    assert code == 400
    assert body["error"] == "bad_start"


def test_install_and_docs_mention_hours():
    from repo_layout import ROOT

    docs = (ROOT / "jeeves" / "docs" / "webhooks.md").read_text(encoding="utf-8")
    assert "/bob/v1/hours" in docs
    install = (ROOT / "jeeves" / "scripts" / "Install-BobWebhooks.ps1").read_text(
        encoding="utf-8-sig"
    )
    assert "bob/v1/hours" in install


def test_oversized_body_413(tmp_path: Path):
    huge = json.dumps(_create_body(idempotency_key="big", description="x" * 70000))
    code, payload, _ = bobhours.handle_hours_request(
        "POST", "/bob/v1/hours", huge.encode("utf-8"), tmp_path
    )
    assert code == 413
    assert json.loads(payload)["error"] == "payload_too_large"
