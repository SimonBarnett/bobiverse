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
    assert "opencode_windows" in payload
    assert payload["pcent"]["opencode-go"] == 28

    # Actual serialized emitter body (not a hand-built dict bypass).
    wire = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
    parsed = bobcallback._parse_json_body(wire, scan_secret=True)
    assert isinstance(parsed, dict)
    assert "opencode_windows" in parsed

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
    assert exported.get("pcent", {}).get("opencode-go") == 28
    _assert_slab_windows(exported["opencode_windows"])

    # Digest-only tray consumption boundary (export_machine_for_tray keys).
    ent = (bobreport.load_digest(tmp_path).get("machines") or {}).get(MID) or {}
    tray = bobreport.export_machine_for_tray(tmp_path, MID, ent)
    assert tray.get("pcent", {}).get("opencode-go") == 28
    _assert_slab_windows(tray["opencode_windows"])


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
    wins = exported["opencode_windows"]
    for wid in ("rolling", "week", "month"):
        assert wins[wid]["status"] == "unknown"
        assert wins[wid].get("used_pct") is None
        assert wins[wid].get("remaining_pct") is None
    assert "opencode-go" not in (exported.get("pcent") or {})


def test_fr6265_pre_6147_merge_field_list_drops_windows_pin():
    """Pin the deployed-hub class: without opencode_windows in MERGE fields, pcent
    survives and windows vanish (5f0ac20a / PR #6212 vs a40d3bbe / FR #6147)."""
    assert "opencode_windows" in bobreport._MERGE_PEER_FIELDS
    assert "opencode_windows" in bobreport._TRAY_MACHINE_EXPORT_KEYS

    doc = {"v": 1, "machines": {}}
    stale_fields = tuple(
        k for k in bobreport._MERGE_PEER_FIELDS if k != "opencode_windows"
    )
    payload = {
        "op": "merge",
        "machine": MID,
        "pcent": {"opencode-go": 28},
        "opencode_windows": SLAB_WINDOWS,
        "lastSeen": FETCHED,
    }
    # Simulate pre-6147 hub: temporarily drop the field from the allowlist.
    original = bobreport._MERGE_PEER_FIELDS
    try:
        bobreport._MERGE_PEER_FIELDS = stale_fields
        bobreport._apply_merge_payload(doc, MID, payload)
    finally:
        bobreport._MERGE_PEER_FIELDS = original
    ent = doc["machines"][MID]
    assert ent["pcent"]["opencode-go"] == 28
    assert "opencode_windows" not in ent

    # Current allowlist retains windows (control).
    doc2 = {"v": 1, "machines": {}}
    bobreport._apply_merge_payload(doc2, MID, payload)
    assert "opencode_windows" in doc2["machines"][MID]
    _assert_slab_windows(doc2["machines"][MID]["opencode_windows"])
