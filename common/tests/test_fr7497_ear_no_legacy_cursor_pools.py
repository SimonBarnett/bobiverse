"""FR #7497: ear fuel publish never emits legacy Grok-chat/Cursor pool fields."""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import bobreport
import bobstat


MID = "marchhare"

# Legacy Cursor-bridge fields that must never leave the ear publish path.
LEGACY_TOP = (
    "cursor_label",
    "cursor_pools",
    "cursor_period_end",
    "sand_period_end",
    "cursor_known",
    "overage_gbp",
    "overage_usd",
    "overspend_state",
    "on_demand_used_cents",
    "on_demand_limit_cents",
    "on_demand_remaining_pct",
    "usd_gbp_rate",
)
LEGACY_PCENT = ("grok-chat", "cursor-models", "cursor_models", "grok_chat")


def _peer_with_legacy_cache(**extra):
    base = {
        "ok": True,
        "id": MID,
        "online": True,
        "status": "operational",
        "weekly": 55,
        "weekly_known": True,
        "pcent": {
            "grok-chat": 74,
            "cursor-models": 74,
            "grok-build": 55,
        },
        "cursor_label": "74%",
        "cursor_pools": [
            {"group_id": "grok-chat", "remaining_pct": 74, "machine_id": MID},
            {"group_id": "cursor-models", "remaining_pct": 74, "machine_id": MID},
        ],
        "cursor_period_end": "11/14/2026 12:58:59",
        "sand_period_end": "11/14/2026 12:58:59",
        "cursor_known": True,
        "overage_gbp": 1.23,
        "overage_usd": 1.5,
        "overspend_state": "ok",
        "on_demand_used_cents": 10,
        "on_demand_limit_cents": 100,
        "on_demand_remaining_pct": 90,
        "overage_fetched_at": "11/07/2026",
        "usd_gbp_rate": 0.79,
        "xai_weekly": {
            "remaining_pct": 55,
            "fetched_at": "2026-11-15T14:31:02Z",
            "source": "cli-chat-proxy",
        },
        "lastSeen": "2026-11-15T14:31:02Z",
    }
    base.update(extra)
    return base


def _assert_no_legacy(payload: dict) -> None:
    assert payload is not None
    for key in LEGACY_TOP:
        assert key not in payload, f"legacy field still published: {key}"
    pcent = payload.get("pcent")
    if isinstance(pcent, dict):
        for key in LEGACY_PCENT:
            assert key not in pcent, f"legacy pcent still published: {key}"
    # xAI one-pool reading must survive.
    assert isinstance(payload.get("xai_weekly"), dict)
    assert payload["xai_weekly"].get("remaining_pct") == 55


def test_fr7497_builder_strips_legacy_even_when_peer_cache_has_them():
    peer = _peer_with_legacy_cache()
    body = bobreport.build_peer_fuel_merge_payload(peer, MID)
    _assert_no_legacy(body)
    # Non-legacy OpenCode / grok-build pcent may remain; grok-build kept here.
    assert body.get("pcent", {}).get("grok-build") == 55
    # Sticky clear so chair drops leftover digest fields.
    cleared = body.get("cleared") or []
    for key in (
        "cursor_label",
        "cursor_pools",
        "cursor_period_end",
        "sand_period_end",
        "cursor_known",
        "overage_gbp",
        "overage_usd",
        "overspend_state",
    ):
        assert key in cleared, f"missing cleared[] for {key}"


def test_fr7497_publish_wire_omits_legacy(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    bobstat.write_peer(home, _peer_with_legacy_cache())
    posted: list[dict] = []

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        posted.append(json.loads(req.data.decode("utf-8")))

        class Resp:
            status = 204

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b""

        return Resp()

    monkeypatch.setattr(bobreport, "fetch_live_xai_weekly", lambda **k: None)
    monkeypatch.setattr(bobreport, "pool_fetch_due", lambda *a, **k: False)
    with mock.patch("urllib.request.urlopen", fake_urlopen):
        code = bobreport.publish_local_peer_fuel(
            home, MID, force=True, url="https://example.test/bob/v1/report"
        )
    assert code == 204
    assert len(posted) == 1
    _assert_no_legacy(posted[0])
