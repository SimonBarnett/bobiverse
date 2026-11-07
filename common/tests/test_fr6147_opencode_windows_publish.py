"""FR #6147: ear digest publish carries OpenCode Go windows + free/go pcent."""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import bobreport
import opencode_fuel as of

# Clarification fixture: free=100 + rolling unstarted; week 72/28 reset 1d 2h; month 36/64 reset 26d 18h.
FIXTURE_CLARIFICATION = json.dumps(
    {
        "costs": {"glm-5.3": 5.4},
        "free_models": ["beam-free"],
        "windows": {
            "rolling": {"status": "unstarted", "used_pct": 0},
            "week": {
                "status": "known",
                "used_pct": 72,
                "remaining_pct": 28,
                "reset_label": "1d 2h",
            },
            "month": {
                "status": "known",
                "used_pct": 36,
                "remaining_pct": 64,
                "reset_label": "26d 18h",
            },
        },
    }
)

FIXTURE_EXHAUSTED_WEEK = json.dumps(
    {
        "free_models": ["beam-free"],
        "windows": {
            "rolling": {"status": "unstarted", "used_pct": 0},
            "week": {
                "status": "exhausted",
                "used_pct": 100,
                "remaining_pct": 0,
                "reset_label": "1d 2h",
            },
            "month": {
                "status": "known",
                "used_pct": 36,
                "remaining_pct": 64,
                "reset_label": "26d 18h",
            },
        },
    }
)

WINDOWS_ONLY_UNKNOWN = json.dumps(
    {
        "rolling": {"status": "unstarted", "used_pct": 0},
        "week": {"status": "unknown"},
        "month": {"status": "unknown"},
    }
)


def _fake_urlopen(posted: list):
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

    return fake_urlopen


def test_fr6147_export_keys_include_opencode_windows():
    assert "opencode_windows" in bobreport._MERGE_PEER_FIELDS
    assert "opencode_windows" in bobreport._TRAY_MACHINE_EXPORT_KEYS


def test_fr6147_read_clarification_fixture_pcent_and_windows(monkeypatch):
    bobreport.clear_opencode_pcent_cache()
    monkeypatch.setenv("BOB_OPENCODE_FUEL_FIXTURE", FIXTURE_CLARIFICATION)
    monkeypatch.delenv("BOB_OPENCODE_WINDOWS_FIXTURE", raising=False)
    monkeypatch.delenv("BOB_OPENCODE_FUEL_HELPER", raising=False)

    pcent = bobreport.read_local_opencode_pcent()
    assert pcent.get("opencode-free") == 100
    # Limiting week remaining wins over month-only cost math.
    assert pcent.get("opencode-go") == 28

    wins = bobreport.read_local_opencode_windows()
    assert wins["rolling"]["status"] == "unstarted"
    assert wins["rolling"]["used_pct"] == 0
    assert wins["week"]["used_pct"] == 72
    assert wins["week"]["remaining_pct"] == 28
    assert wins["week"]["reset_label"] == "1d 2h"
    assert wins["month"]["used_pct"] == 36
    assert wins["month"]["remaining_pct"] == 64
    assert wins["month"]["reset_label"] == "26d 18h"
    lim, rem = of.limiting_go_window(wins)
    assert lim == "week" and rem == 28


def test_fr6147_peer_merge_carries_pcent_and_windows(tmp_path: Path, monkeypatch):
    import bobstat

    bobreport.clear_opencode_pcent_cache()
    monkeypatch.setenv("BOB_OPENCODE_FUEL_FIXTURE", FIXTURE_CLARIFICATION)
    home = tmp_path / "home"
    home.mkdir()
    mid = "marchhare"
    bobstat.write_peer(
        home,
        {
            "ok": True,
            "id": mid,
            "online": True,
            "status": "operational",
            "weekly": 80,
            "weekly_known": True,
            "pcent": {"grok-chat": 42},
            "lastSeen": "2026-11-07T12:00:00Z",
        },
    )
    posted: list[dict] = []
    with mock.patch("urllib.request.urlopen", _fake_urlopen(posted)):
        code = bobreport.publish_local_peer_fuel(
            home, mid, force=True, url="https://example.test/bob/v1/report"
        )
    assert code == 204
    body = posted[0]
    assert body["pcent"]["opencode-free"] == 100
    assert body["pcent"]["opencode-go"] == 28
    wins = body["opencode_windows"]
    assert wins["rolling"]["status"] == "unstarted"
    assert wins["week"]["remaining_pct"] == 28
    assert wins["week"]["reset_label"] == "1d 2h"
    assert wins["month"]["remaining_pct"] == 64
    assert wins["month"]["reset_label"] == "26d 18h"


def test_fr6147_exhausted_week_go_remaining_zero(tmp_path: Path, monkeypatch):
    import bobstat

    bobreport.clear_opencode_pcent_cache()
    monkeypatch.setenv("BOB_OPENCODE_FUEL_FIXTURE", FIXTURE_EXHAUSTED_WEEK)
    home = tmp_path / "home"
    home.mkdir()
    mid = "redqueen"
    bobstat.write_peer(
        home,
        {
            "ok": True,
            "id": mid,
            "online": True,
            "status": "operational",
            "weekly": 80,
            "weekly_known": True,
            "pcent": {},
            "lastSeen": "2026-11-07T12:00:00Z",
        },
    )
    posted: list[dict] = []
    with mock.patch("urllib.request.urlopen", _fake_urlopen(posted)):
        code = bobreport.publish_local_peer_fuel(
            home, mid, force=True, url="https://example.test/bob/v1/report"
        )
    assert code == 204
    body = posted[0]
    assert body["pcent"]["opencode-free"] == 100
    assert body["pcent"]["opencode-go"] == 0
    assert body["opencode_windows"]["week"]["status"] == "exhausted"
    assert body["opencode_windows"]["week"]["remaining_pct"] == 0
    lim, rem = of.limiting_go_window(body["opencode_windows"])
    assert lim == "week" and rem == 0


def test_fr6147_unknown_omits_pcent_zeros_windows_may_remain(monkeypatch):
    bobreport.clear_opencode_pcent_cache()
    monkeypatch.delenv("BOB_OPENCODE_FUEL_FIXTURE", raising=False)
    monkeypatch.setenv("BOB_OPENCODE_WINDOWS_FIXTURE", WINDOWS_ONLY_UNKNOWN)
    monkeypatch.setenv(
        "BOB_OPENCODE_FUEL_HELPER", str(Path("C:/no/such/Get-BobOpencodeFuel.ps1"))
    )

    pcent = bobreport.read_local_opencode_pcent()
    assert "opencode-free" not in pcent
    assert "opencode-go" not in pcent

    wins = bobreport.read_local_opencode_windows()
    assert wins["rolling"]["status"] == "unstarted"
    assert wins["week"]["status"] == "unknown"
    assert wins["month"]["status"] == "unknown"

    peer = {"id": "marchhare", "pcent": {"grok-chat": 10}}
    enriched = bobreport.enrich_peer_with_opencode_pcent(peer, pcent, wins)
    assert "opencode-free" not in enriched["pcent"]
    assert "opencode-go" not in enriched["pcent"]
    assert enriched["opencode_windows"]["rolling"]["status"] == "unstarted"


def test_fr6147_export_machine_for_tray_keeps_opencode_windows(tmp_path: Path):
    home = tmp_path / "digest"
    home.mkdir()
    doc = bobreport.empty_digest()
    wins = of.normalize_go_windows(
        {
            "rolling": {"status": "unstarted", "used_pct": 0},
            "week": {"status": "known", "used_pct": 72, "remaining_pct": 28},
            "month": {"status": "known", "used_pct": 36, "remaining_pct": 64},
        }
    )
    doc["machines"]["marchhare"] = {
        "online": True,
        "pcent": {"opencode-free": 100, "opencode-go": 28},
        "opencode_windows": wins,
    }
    bobreport.save_digest(home, doc)
    exported = bobreport.export_machine_for_tray(
        home, "marchhare", doc["machines"]["marchhare"]
    )
    assert exported["pcent"]["opencode-go"] == 28
    assert exported["opencode_windows"]["week"]["remaining_pct"] == 28


def test_mrb6232_peer_fuel_fingerprint_includes_opencode_windows():
    import bobreport as br

    base = {"id": "marchhare", "pcent": {"opencode-free": 100, "opencode-go": 28}}
    a = dict(base)
    a["opencode_windows"] = {"week": {"remaining_pct": 28, "status": "known"}}
    b = dict(base)
    b["opencode_windows"] = {"week": {"remaining_pct": 10, "status": "known"}}
    assert br.peer_fuel_fingerprint(a) != br.peer_fuel_fingerprint(b)

