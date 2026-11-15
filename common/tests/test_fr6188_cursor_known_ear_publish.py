"""FR #6188 / #7497: cursor_known is no longer ear-published (xAI is xai_weekly only).

Historical FR #6188 required tri-state cursor_known on the wire. FR #7497 retires
Cursor-bridge leftovers from ear publish; cursor_known must be absent and listed
in cleared[] so sticky digest values drop.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import bobreport
import bobstat


MID = "redqueen"


def _peer(**extra):
    base = {
        "ok": True,
        "id": MID,
        "online": True,
        "status": "operational",
        "weekly": 80,
        "weekly_known": True,
        "remaining_pct": 42,
        "pcent": {"grok-chat": 42, "cursor-models": 10, "grok-build": 80},
        "cursor_pools": [
            {"group_id": "grok-chat", "remaining_pct": 42, "machine_id": MID},
        ],
        "xai_weekly": {"remaining_pct": 80, "fetched_at": "2026-11-15T14:00:00Z"},
        "lastSeen": "2026-11-07T12:00:00Z",
    }
    base.update(extra)
    return base


def test_fr6188_builder_cursor_known_retired_by_fr7497():
    for flag in (True, False, "false", None):
        peer = _peer()
        if flag is None:
            peer.pop("cursor_known", None)
        else:
            peer["cursor_known"] = flag
        body = bobreport.build_peer_fuel_merge_payload(peer, MID)
        assert body is not None
        assert "weekly_known" in body
        assert body["weekly_known"] is True
        assert "cursor_known" not in body
        assert "cursor_known" in (body.get("cleared") or [])
        assert "cursor_pools" not in body
        assert "grok-chat" not in (body.get("pcent") or {})
        assert isinstance(body.get("xai_weekly"), dict)


def test_fr6188_publish_wire_omits_cursor_known(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    peer = _peer(cursor_known=False)
    bobstat.write_peer(home, peer)
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
    assert "cursor_known" not in posted[0]
    assert "cursor_known" in (posted[0].get("cleared") or [])


def test_fr6188_fingerprint_still_posts_on_xai_change(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("BOB_EAR_DIGEST_FUEL_S", "30")
    peer = _peer()
    bobstat.write_peer(home, peer)
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

    monkeypatch.setattr(bobstat, "refresh_peer_cursor_remaining", lambda *a, **k: False)
    monkeypatch.setattr(bobreport, "read_local_opencode_pcent", lambda *a, **k: {})
    monkeypatch.setattr(bobreport, "fetch_live_xai_weekly", lambda **k: None)
    monkeypatch.setattr(bobreport, "pool_fetch_due", lambda *a, **k: False)

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        assert (
            bobreport.publish_local_peer_fuel(
                home, MID, force=False, url="https://example.test/bob/v1/report", now=100.0
            )
            == 204
        )
        peer2 = dict(peer)
        peer2["xai_weekly"] = {"remaining_pct": 79, "fetched_at": "2026-11-15T14:01:00Z"}
        bobstat.write_peer(home, peer2)
        assert (
            bobreport.publish_local_peer_fuel(
                home, MID, force=False, url="https://example.test/bob/v1/report", now=101.0
            )
            == 204
        )
        # identical republish suppressed
        assert (
            bobreport.publish_local_peer_fuel(
                home, MID, force=False, url="https://example.test/bob/v1/report", now=102.0
            )
            is None
        )

    assert len(posted) == 2
    assert all("cursor_known" not in p for p in posted)
