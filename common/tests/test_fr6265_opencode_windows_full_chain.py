"""FR #6265: full-chain OpenCode windows survive serialize -> hub -> tray export.

Live gap (Slab 2026-11-08): emitter post-state and payload_keys included
opencode_windows (rolling 0/100, week 72/28, month 36/64, source go-zen-usage)
and HTTP 204, but public GET retained pcent.opencode-go=28 with opencode_windows
absent. Deployed hub jeeves.exe was built from 5f0ac20a (PR #6212), which
predates FR #6147 (a40d3bbe) adding opencode_windows to _MERGE_PEER_FIELDS.
Current main already retains/exports the field; this module pins the wire
regression and the pre-6147 drop so a stale hub cannot be mistaken for a
sender bug. Reset labels that are already null emitter-side stay null.
"""
from __future__ import annotations

import json
from pathlib import Path

import bobcallback
import bobreport
import opencode_fuel as of

MID = "marchhare"
FETCHED = "2026-11-08T22:58:20.863353Z"

# Matches Slab evidence-6263-payload-vs-hub-2258.json retained emitter windows.
SLAB_WINDOWS = {
    "rolling": {
        "status": "known",
        "used_pct": 0,
        "remaining_pct": 100,
        "reset_label": None,
        "source": of.GO_ZEN_USAGE_SOURCE,
        "fetched_at": FETCHED,
    },
    "week": {
        "status": "known",
        "used_pct": 72,
        "remaining_pct": 28,
        "reset_label": None,
        "source": of.GO_ZEN_USAGE_SOURCE,
        "fetched_at": FETCHED,
    },
    "month": {
        "status": "known",
        "used_pct": 36,
        "remaining_pct": 64,
        "reset_label": None,
        "source": of.GO_ZEN_USAGE_SOURCE,
        "fetched_at": FETCHED,
    },
}


def _roster(home: Path) -> None:
    (home / "registered-machines.json").write_text(
        json.dumps({"v": 1, "machines": [MID]}),
        encoding="utf-8",
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None


def _assert_slab_windows(wins: dict) -> None:
    assert isinstance(wins, dict)
    for wid, used, rem in (
        ("rolling", 0, 100),
        ("week", 72, 28),
        ("month", 36, 64),
    ):
        rec = wins[wid]
        assert rec["status"] == "known"
        assert rec["used_pct"] == used
        assert rec["remaining_pct"] == rem
        assert rec["source"] == of.GO_ZEN_USAGE_SOURCE
        assert rec["fetched_at"] == FETCHED
        # Emitter already null: hub/tray must not fabricate a reset string.
        assert rec.get("reset_label") is None


def test_fr6265_serialized_payload_survives_receiver_digest_and_tray_export(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _roster(tmp_path)

    peer = {
        "id": MID,
        "ok": True,
        "online": True,
        "status": "operational",
        "pcent": {"opencode-go": 28, "grok-chat": 74},
        "opencode_windows": SLAB_WINDOWS,
        "lastSeen": FETCHED,
    }
    payload = bobreport.build_peer_fuel_merge_payload(peer, MID)
    assert payload is not None
    assert "opencode_windows" not in payload
    assert "opencode-go" not in (payload.get("pcent") or {})
    # FR #7752 / #7497: grok-chat is a Cursor-bridge pcent key and is not published.
    assert "grok-chat" not in (payload.get("pcent") or {})

    # Actual serialized emitter body (not a hand-built dict bypass).
    wire = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
    parsed = bobcallback._parse_json_body(wire, scan_secret=True)
    assert isinstance(parsed, dict)
    assert "opencode_windows" not in parsed

    code, _body = bobcallback.handle_report_post(
        {"Content-Type": "application/json"},
        wire,
        tmp_path,
        briefer_nick="Jeeves",
    )
    assert code in (200, 204), code

    digest = bobreport.build_digest_object(tmp_path, "Jeeves")
    machines = digest.get("machines") or {}
    exported = machines.get(MID) or {}
    # FR #7366: fleet OpenCode is not echoed per machine.
    assert "opencode-go" not in (exported.get("pcent") or {})
    assert "opencode_windows" not in exported
    assert "grok-chat" not in (exported.get("pcent") or {})

    ent = (bobreport.load_digest(tmp_path).get("machines") or {}).get(MID) or {}
    tray = bobreport.export_machine_for_tray(tmp_path, MID, ent)
    assert "opencode-go" not in (tray.get("pcent") or {})
    assert "opencode_windows" not in tray


def test_fr6265_unknown_window_never_becomes_zero_through_chain(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _roster(tmp_path)
    unknown = of.normalize_go_windows(
        {
            "rolling": {"status": "unknown"},
            "week": {"status": "unknown"},
            "month": {"status": "unknown"},
        }
    )
    peer = {
        "id": MID,
        "ok": True,
        "online": True,
        "status": "operational",
        "opencode_windows": unknown,
        "pcent": {"grok-chat": 10},
    }
    payload = bobreport.build_peer_fuel_merge_payload(peer, MID)
    assert payload is not None
    wire = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
    code, _ = bobcallback.handle_report_post(
        {"Content-Type": "application/json"},
        wire,
        tmp_path,
        briefer_nick="Jeeves",
    )
    assert code in (200, 204), code
    exported = (bobreport.build_digest_object(tmp_path, "Jeeves").get("machines") or {}).get(
        MID
    ) or {}
    assert "opencode_windows" not in exported
    assert "opencode-go" not in (exported.get("pcent") or {})


def test_fr6265_pre_6147_merge_field_list_drops_windows_pin():
    """FR #7366: machine merge never retains fleet OpenCode windows or pcent.opencode-go."""
    assert "opencode_windows" not in bobreport._MERGE_PEER_FIELDS
    assert "opencode_windows" not in bobreport._TRAY_MACHINE_EXPORT_KEYS

    payload = {
        "op": "merge",
        "machine": MID,
        "pcent": {"opencode-go": 28, "grok-chat": 10},
        "opencode_windows": SLAB_WINDOWS,
        "lastSeen": FETCHED,
    }
    doc2 = {"v": 1, "machines": {}}
    bobreport._apply_merge_payload(doc2, MID, payload)
    ent = doc2["machines"][MID]
    assert "opencode_windows" not in ent
    assert "opencode-go" not in (ent.get("pcent") or {})
    assert ent["pcent"]["grok-chat"] == 10
