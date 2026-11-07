"""Digest / webhook tests for OpenCode fuel ids (issue #6120)."""
from __future__ import annotations

from pathlib import Path

import bobreport


def test_pcent_retains_opencode_fuel_ids(tmp_path: Path):
    raw = {
        "online": True,
        "pcent": {
            "cursor-models": 40,
            "opencode-free": 100,
            "opencode-go": 50,
        },
    }
    ent = bobreport._coerce_machine("marchhare", raw)
    assert ent["pcent"]["opencode-free"] == 100
    assert ent["pcent"]["opencode-go"] == 50


def test_export_machine_for_tray_keeps_opencode_pcent(tmp_path: Path):
    home = tmp_path / "digest"
    home.mkdir()
    doc = bobreport.empty_digest()
    doc["machines"]["marchhare"] = {
        "online": True,
        "pcent": {"opencode-free": 100, "opencode-go": 50},
    }
    bobreport.save_digest(home, doc)
    exported = bobreport.export_machine_for_tray(home, "marchhare", doc["machines"]["marchhare"])
    assert exported["pcent"]["opencode-free"] == 100
    assert exported["pcent"]["opencode-go"] == 50


# --- FR #6146: ear publish includes OpenCode pcent when known ---

FIXTURE_FREE100_GO50 = '{"costs": {"glm-5.3": 7.5}, "free_models": ["beam-free"]}'


def test_fr6146_read_local_opencode_pcent_from_fixture(monkeypatch):
    monkeypatch.setenv("BOB_OPENCODE_FUEL_FIXTURE", FIXTURE_FREE100_GO50)
    monkeypatch.delenv("BOB_OPENCODE_FUEL_HELPER", raising=False)
    got = bobreport.read_local_opencode_pcent()
    assert got.get("opencode-free") == 100
    assert got.get("opencode-go") == 50
    # Never invent unknown keys as 0
    assert "opencode-free" in got and "opencode-go" in got


def test_fr6146_read_local_opencode_pcent_unknown_omits(monkeypatch):
    monkeypatch.delenv("BOB_OPENCODE_FUEL_FIXTURE", raising=False)
    # Force helper miss so live CLI is not required
    monkeypatch.setenv("BOB_OPENCODE_FUEL_HELPER", str(Path("C:/no/such/Get-BobOpencodeFuel.ps1")))
    got = bobreport.read_local_opencode_pcent()
    assert got == {}
    assert "opencode-free" not in got
    assert "opencode-go" not in got


def test_fr6146_enrich_peer_merges_known_only():
    peer = {"id": "redqueen", "pcent": {"grok-chat": 42}}
    enriched = bobreport.enrich_peer_with_opencode_pcent(
        peer, {"opencode-free": 100, "opencode-go": 50}
    )
    assert enriched["pcent"]["grok-chat"] == 42
    assert enriched["pcent"]["opencode-free"] == 100
    assert enriched["pcent"]["opencode-go"] == 50
    # empty/unknown: no invent
    peer2 = {"id": "redqueen", "pcent": {"grok-chat": 42}}
    enriched2 = bobreport.enrich_peer_with_opencode_pcent(peer2, {})
    assert "opencode-free" not in enriched2["pcent"]
    assert "opencode-go" not in enriched2["pcent"]
    # None values omitted; explicit 0 (exhausted) kept
    peer3 = {"id": "redqueen", "pcent": {}}
    enriched3 = bobreport.enrich_peer_with_opencode_pcent(
        peer3, {"opencode-free": None, "opencode-go": 0}
    )
    assert "opencode-free" not in enriched3["pcent"]
    assert enriched3["pcent"]["opencode-go"] == 0


def test_fr6146_publish_round_trip_fixture(tmp_path: Path, monkeypatch):
    """Fixture free=100 go=50 -> merge payload pcent keys match (FR #6146)."""
    import json
    from unittest import mock

    import bobstat

    monkeypatch.setenv("BOB_OPENCODE_FUEL_FIXTURE", FIXTURE_FREE100_GO50)
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
        code = bobreport.publish_local_peer_fuel(
            home, mid, force=True, url="https://example.test/bob/v1/report"
        )
    assert code == 204
    assert len(posted) == 1
    body = posted[0]
    assert body.get("op") == "merge"
    assert body["pcent"]["opencode-free"] == 100
    assert body["pcent"]["opencode-go"] == 50
    assert body["pcent"]["grok-chat"] == 42
    blob = json.dumps(body)
    assert not bobreport.looks_like_secret(blob)


def test_fr6146_publish_omits_opencode_when_unknown(tmp_path: Path, monkeypatch):
    import json
    from unittest import mock

    import bobstat

    monkeypatch.delenv("BOB_OPENCODE_FUEL_FIXTURE", raising=False)
    monkeypatch.setenv("BOB_OPENCODE_FUEL_HELPER", str(Path("C:/no/such/Get-BobOpencodeFuel.ps1")))
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
        code = bobreport.publish_local_peer_fuel(
            home, mid, force=True, url="https://example.test/bob/v1/report"
        )
    assert code == 204
    body = posted[0]
    pcent = body.get("pcent") or {}
    assert "opencode-free" not in pcent
    assert "opencode-go" not in pcent
    assert pcent.get("grok-chat") == 42
