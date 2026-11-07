"""FR #6188: ear publish payload emits cursor_known (tri-state; fingerprint delta)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import bobreport
import bobstat
import pytest


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
        "pcent": {"grok-chat": 42, "cursor-models": 10},
        "cursor_pools": [
            {"group_id": "grok-chat", "remaining_pct": 42, "machine_id": MID},
        ],
        "lastSeen": "2026-11-07T12:00:00Z",
    }
    base.update(extra)
    return base


@pytest.mark.parametrize(
    "flag,expect_present,expect_value",
    [
        (True, True, True),
        (False, True, False),
        ("false", True, False),
        (None, False, None),  # explicit null -> omit
        ("__omit__", False, None),
    ],
)
def test_fr6188_builder_cursor_known_tri_state(flag, expect_present, expect_value):
    peer = _peer()
    if flag == "__omit__":
        peer.pop("cursor_known", None)
    else:
        peer["cursor_known"] = flag
    body = bobreport.build_peer_fuel_merge_payload(peer, MID)
    assert body is not None
    assert "weekly_known" in body
    assert body["weekly_known"] is True
    if expect_present:
        assert "cursor_known" in body
        assert body["cursor_known"] is expect_value
        assert isinstance(body["cursor_known"], bool)
    else:
        assert "cursor_known" not in body


def test_fr6188_publish_wire_json_boolean(tmp_path: Path):
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

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        code = bobreport.publish_local_peer_fuel(
            home, MID, force=True, url="https://example.test/bob/v1/report"
        )
    assert code == 204
    assert len(posted) == 1
    assert posted[0]["cursor_known"] is False
    assert isinstance(posted[0]["cursor_known"], bool)


def test_fr6188_flag_only_change_posts_without_force(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("BOB_EAR_DIGEST_FUEL_S", "30")
    peer = _peer(cursor_known=True)
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

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        assert (
            bobreport.publish_local_peer_fuel(
                home, MID, force=False, url="https://example.test/bob/v1/report", now=100.0
            )
            == 204
        )
        peer_false = dict(peer)
        peer_false["cursor_known"] = False
        bobstat.write_peer(home, peer_false)
        assert (
            bobreport.publish_local_peer_fuel(
                home, MID, force=False, url="https://example.test/bob/v1/report", now=101.0
            )
            == 204
        )
        peer_true = dict(peer_false)
        peer_true["cursor_known"] = True
        bobstat.write_peer(home, peer_true)
        assert (
            bobreport.publish_local_peer_fuel(
                home, MID, force=False, url="https://example.test/bob/v1/report", now=102.0
            )
            == 204
        )
        # identical republish suppressed
        assert (
            bobreport.publish_local_peer_fuel(
                home, MID, force=False, url="https://example.test/bob/v1/report", now=103.0
            )
            is None
        )

    assert len(posted) == 3
    assert [p["cursor_known"] for p in posted] == [True, False, True]


def test_fr6188_normalize_helper_tri_state():
    assert bobreport._normalize_peer_cursor_known({"cursor_known": True}) is True
    assert bobreport._normalize_peer_cursor_known({"cursor_known": False}) is False
    assert bobreport._normalize_peer_cursor_known({"cursor_known": "false"}) is False
    assert bobreport._normalize_peer_cursor_known({"cursor_known": None}) is None
    assert bobreport._normalize_peer_cursor_known({}) is None
