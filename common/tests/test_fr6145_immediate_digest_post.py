"""FR #6145 / FR-005: Immediate digest POST when pool remaining changes."""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import bobreport
import bobstat


def test_fr6145_fingerprint_includes_remaining_opencode_copilot_account():
    peer = {
        "weekly": 50,
        "remaining_pct": 40,
        "grok_account": "user@example.test",
        "overage_fetched_at": "2026-11-07T12:00:00Z",
        "pcent": {
            "grok-chat": 40,
            "opencode-free": 80,
            "opencode-go": 20,
        },
        "cursor_pools": [{"group_id": "g", "remaining_pct": 40}],
    }
    fp = bobreport.peer_fuel_fingerprint(peer)
    assert "remaining_pct=40" in fp
    assert "grok_account=user@example.test" in fp
    assert "overage_fetched_at=2026-11-07T12:00:00Z" in fp
    assert "opencode-free" in fp
    assert "opencode-go" in fp
    peer2 = dict(peer)
    peer2["remaining_pct"] = 39
    assert bobreport.peer_fuel_fingerprint(peer2) != fp
    peer3 = dict(peer)
    peer3["overage_fetched_at"] = "2026-11-07T12:00:05Z"
    assert bobreport.peer_fuel_fingerprint(peer3) != fp
    peer4 = dict(peer)
    peer4["grok_account"] = "other@example.test"
    assert bobreport.peer_fuel_fingerprint(peer4) != fp
    peer5 = dict(peer)
    peer5["pcent"] = dict(peer["pcent"])
    peer5["pcent"]["opencode-free"] = 79
    assert bobreport.peer_fuel_fingerprint(peer5) != fp


def test_fr6145_delta_s_default_and_env(monkeypatch):
    monkeypatch.delenv("BOB_EAR_DIGEST_FUEL_DELTA_S", raising=False)
    assert bobreport.digest_fuel_delta_s() == 5.0
    assert bobreport.DIGEST_FUEL_MAX_LAG_S == 5.0
    monkeypatch.setenv("BOB_EAR_DIGEST_FUEL_DELTA_S", "3")
    assert bobreport.digest_fuel_delta_s() == 3.0


def test_fr6145_unchanged_fingerprint_skips_post(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    mid = "redqueen"
    peer = {
        "ok": True,
        "id": mid,
        "online": True,
        "status": "operational",
        "weekly": 80,
        "weekly_known": True,
        "remaining_pct": 42,
        "pcent": {"grok-chat": 42},
        "lastSeen": "2026-11-07T12:00:00Z",
    }
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
        assert (
            bobreport.publish_local_peer_fuel(
                home, mid, url="https://example.test/bob/v1/report", now=1.0
            )
            == 204
        )
        assert (
            bobreport.publish_local_peer_fuel(
                home, mid, url="https://example.test/bob/v1/report", now=2.0
            )
            is None
        )
    assert len(posted) == 1


def test_fr6145_remaining_delta_posts_without_force(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    mid = "redqueen"
    peer = {
        "ok": True,
        "id": mid,
        "online": True,
        "status": "operational",
        "weekly": 80,
        "weekly_known": True,
        "remaining_pct": 42,
        "pcent": {"grok-chat": 42, "opencode-free": 90},
        "overage_fetched_at": "2026-11-01T00:00:00Z",
        "lastSeen": "2026-11-07T12:00:00Z",
    }
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
        bobreport.publish_local_peer_fuel(
            home, mid, url="https://example.test/bob/v1/report", now=10.0
        )
        peer2 = dict(peer)
        peer2["remaining_pct"] = 41
        peer2["pcent"] = {"grok-chat": 41, "opencode-free": 90}
        bobstat.write_peer(home, peer2)
        code = bobreport.publish_local_peer_fuel(
            home, mid, force=False, url="https://example.test/bob/v1/report", now=11.0
        )
    assert code == 204
    assert len(posted) == 2
    assert posted[1].get("remaining_pct") == 41


def test_fr6145_copilot_fetched_at_delta_posts(tmp_path: Path):
    """Stale multi-day overage_fetched_at must POST when refresh updates the stamp."""
    home = tmp_path / "home"
    home.mkdir()
    mid = "redqueen"
    peer = {
        "ok": True,
        "id": mid,
        "online": True,
        "status": "operational",
        "weekly": 10,
        "weekly_known": True,
        "remaining_pct": 10,
        "overage_fetched_at": "2026-11-01T00:00:00Z",
        "lastSeen": "2026-11-07T12:00:00Z",
    }
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
        bobreport.publish_local_peer_fuel(
            home, mid, url="https://example.test/bob/v1/report", now=100.0
        )
        peer2 = dict(peer)
        peer2["overage_fetched_at"] = "2026-11-07T14:00:00Z"
        bobstat.write_peer(home, peer2)
        code = bobreport.publish_local_peer_fuel(
            home, mid, force=False, url="https://example.test/bob/v1/report", now=101.0
        )
    assert code == 204
    assert len(posted) == 2
    assert posted[1].get("overage_fetched_at") == "2026-11-07T14:00:00Z"


def test_fr6145_ear_tick_uses_delta_s_not_only_heartbeat():
    src = (Path(__file__).resolve().parents[1] / "scripts" / "irc_agent.py").read_text(
        encoding="utf-8"
    )
    assert "FR #6145" in src or "digest_fuel_delta_s" in src
    block = src[src.index("def _maybe_publish_digest_fuel") : src.index("def _maybe_publish_digest_fuel") + 900]
    assert "digest_fuel_delta_s" in block
    # Must not gate solely on heartbeat (30s) for delta detection.
    assert "digest_fuel_heartbeat_s" not in block or "digest_fuel_delta_s" in block
