"""FR #8237: ear ingest of the public digest must persist fleet_pools.

Seats fill mid-job Go fuel from local digest.json (FR #8230). The public
/bob/v1/report already carries fleet_pools.opencode-go; ingest_fleet_digest_pull
must write that row onto each machine's digest so workers see it without
calling zen or reading the Go key.
"""
from __future__ import annotations

import json
from pathlib import Path

import bobreport


def _go_row(**kw):
    row = {
        "id": "opencode-go",
        "remaining": 78,
        "fresh": True,
        "fetched_at": "2026-11-18T17:00:00Z",
        "usage_source": "go-zen-usage",
        "windows": {"week": {"remaining_pct": 78}},
    }
    row.update(kw)
    return row


def test_fr8237_ingest_persists_fleet_opencode_go(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    bobreport.save_digest(
        tmp_path,
        {"v": 1, "ts": "2026-11-18T16:00:00Z", "machines": {"flamingo": {"id": "flamingo"}}},
    )
    pull = {
        "v": 1,
        "ts": "2026-11-18T17:05:00Z",
        "briefer": "Jeeves",
        "chairNick": "Jeeves",
        "machines": {"flamingo": {"id": "flamingo", "online": True}},
        "fleet_pools": {
            "opencode-go": _go_row(),
            "copilot": {
                "remaining": 40,
                "fresh": True,
                "fetched_at": "2026-11-18T17:00:00Z",
                "source": "copilot_internal/user",
            },
        },
        "opencode": {"opencode-go": _go_row(), "go": 78},
        "copilot": {
            "remaining": 40,
            "fresh": True,
            "fetched_at": "2026-11-18T17:00:00Z",
            "source": "copilot_internal/user",
        },
        "fleet": {"opencode-go": _go_row()},
    }
    bobreport.ingest_fleet_digest_pull(tmp_path, pull)
    doc = bobreport.load_digest(tmp_path)
    fp = doc.get("fleet_pools") or {}
    assert isinstance(fp.get("opencode-go"), dict)
    assert fp["opencode-go"]["remaining"] == 78
    assert fp["opencode-go"]["fresh"] is True
    assert fp["opencode-go"]["fetched_at"] == "2026-11-18T17:00:00Z"
    assert fp["opencode-go"]["usage_source"] == "go-zen-usage"
    assert isinstance(fp["opencode-go"].get("windows"), dict)
    assert isinstance(fp.get("copilot"), dict)
    assert fp["copilot"]["remaining"] == 40
    assert isinstance(doc.get("opencode"), dict)
    assert doc["opencode"].get("go") == 78
    assert isinstance(doc.get("copilot"), dict)
    assert doc["copilot"]["remaining"] == 40
    # No credential-shaped fields mirrored from the pull.
    blob = json.dumps(doc)
    assert "apikey" not in blob.lower()
    assert "token" not in blob.lower()
    assert "bearer" not in blob.lower()


def test_fr8237_ingest_keeps_local_fleet_when_pull_omits(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    local_go = _go_row(remaining=55)
    bobreport.save_digest(
        tmp_path,
        {
            "v": 1,
            "machines": {"flamingo": {"id": "flamingo"}},
            "fleet_pools": {"opencode-go": local_go},
        },
    )
    pull = {
        "v": 1,
        "ts": "2026-11-18T17:10:00Z",
        "machines": {"flamingo": {"id": "flamingo", "online": True}},
        # No fleet_pools / opencode / copilot — do not wipe the local row.
    }
    bobreport.ingest_fleet_digest_pull(tmp_path, pull)
    doc = bobreport.load_digest(tmp_path)
    assert (doc.get("fleet_pools") or {}).get("opencode-go", {}).get("remaining") == 55


def test_fr8237_ingest_overwrites_stale_local_fleet(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    bobreport.save_digest(
        tmp_path,
        {
            "v": 1,
            "machines": {"flamingo": {"id": "flamingo"}},
            "fleet_pools": {"opencode-go": _go_row(remaining=10, fresh=False)},
        },
    )
    pull = {
        "v": 1,
        "machines": {"flamingo": {"id": "flamingo"}},
        "fleet_pools": {"opencode-go": _go_row(remaining=90)},
    }
    bobreport.ingest_fleet_digest_pull(tmp_path, pull)
    doc = bobreport.load_digest(tmp_path)
    assert (doc.get("fleet_pools") or {})["opencode-go"]["remaining"] == 90
    assert (doc.get("fleet_pools") or {})["opencode-go"]["fresh"] is True
