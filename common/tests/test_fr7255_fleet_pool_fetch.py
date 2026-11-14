"""FR #7255: Jeeves fetches OpenCode + Copilot once per minute for the fleet."""
from __future__ import annotations

from pathlib import Path

import bobreport
import chair_health
import fleet_pool_fetch as fp


def test_fleet_pool_fetch_constant_is_60():
    assert fp.FLEET_POOL_FETCH_S == 60.0
    assert chair_health.COPILOT_TICK_S == 60.0


def test_two_ticks_60s_apart_new_fetched_at(tmp_path: Path):
    home = tmp_path / "digest"
    home.mkdir()
    bobreport.save_digest(home, bobreport.empty_digest())
    t0 = 1_700_000_000.0
    n = {"i": 0}

    def copilot(_home, now):
        iso = fp.iso_utc(now)
        return {
            "id": "copilot",
            "remaining": 80,
            "fetched_at": iso,
            "last_attempt_at": iso,
            "error": None,
            "source": "copilot_internal/user",
            "fresh": True,
        }

    def opencode(_home, now):
        iso = fp.iso_utc(now)
        n["i"] += 1
        return {
            "opencode-free": {
                "id": "opencode-free",
                "remaining": 90,
                "fetched_at": iso,
                "last_attempt_at": iso,
                "error": None,
                "source": "go-zen-usage",
                "fresh": True,
            },
            "opencode-go": {
                "id": "opencode-go",
                "remaining": 70,
                "fetched_at": iso,
                "last_attempt_at": iso,
                "error": None,
                "source": "go-zen-usage",
                "fresh": True,
            },
            "windows": {},
        }

    a = fp.tick_fleet_pools(
        home, now=t0, force=True, fetch_copilot=copilot, fetch_opencode=opencode
    )
    b = fp.tick_fleet_pools(
        home, now=t0 + 60.0, force=True, fetch_copilot=copilot, fetch_opencode=opencode
    )
    assert a["copilot"]["fetched_at"] != b["copilot"]["fetched_at"]
    assert a["opencode-free"]["fetched_at"] != b["opencode-free"]["fetched_at"]
    assert a["opencode-go"]["fetched_at"] != b["opencode-go"]["fetched_at"]
    doc = bobreport.load_digest(home)
    pub = bobreport.build_digest_object(home, "jeeves")
    assert pub.get("fleet_pools")
    assert pub["fleet_pools"]["copilot"]["fetched_at"] == b["copilot"]["fetched_at"]
    assert doc["copilot"]["fetched_at"] == b["copilot"]["fetched_at"]


def test_failure_keeps_fetched_at_stamps_last_attempt(tmp_path: Path):
    home = tmp_path / "digest"
    home.mkdir()
    bobreport.save_digest(home, bobreport.empty_digest())
    t0 = 1_700_000_000.0
    good_iso = fp.iso_utc(t0)

    def copilot_ok(_h, now):
        return {
            "id": "copilot",
            "remaining": 12,
            "fetched_at": fp.iso_utc(now),
            "error": None,
            "source": "copilot_internal/user",
            "fresh": True,
        }

    def oc_ok(_h, now):
        iso = fp.iso_utc(now)
        return {
            "opencode-free": {
                "id": "opencode-free",
                "remaining": 1,
                "fetched_at": iso,
                "error": None,
                "source": "go-zen-usage",
                "fresh": True,
            },
            "opencode-go": {
                "id": "opencode-go",
                "remaining": 2,
                "fetched_at": iso,
                "error": None,
                "source": "go-zen-usage",
                "fresh": True,
            },
        }

    fp.tick_fleet_pools(home, now=t0, force=True, fetch_copilot=copilot_ok, fetch_opencode=oc_ok)

    def copilot_fail(_h, now):
        raise RuntimeError("provider-http-429")

    def oc_fail(_h, now):
        raise RuntimeError("unavailable")

    out = fp.tick_fleet_pools(
        home, now=t0 + 60.0, force=True, fetch_copilot=copilot_fail, fetch_opencode=oc_fail
    )
    assert out["copilot"]["fetched_at"] == good_iso
    assert out["copilot"]["fresh"] is False
    assert out["copilot"]["last_attempt_at"] == fp.iso_utc(t0 + 60.0)
    assert out["copilot"]["error"]
    assert out["opencode-go"]["fetched_at"] == good_iso
    assert out["opencode-go"]["last_attempt_at"] == fp.iso_utc(t0 + 60.0)


def test_ear_publish_does_not_call_copilot_or_opencode(monkeypatch, tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    import bobstat

    bobstat.write_peer(
        home,
        {
            "id": "flamingo",
            "ok": True,
            "online": True,
            "status": "operational",
            "weekly": 10,
            "weekly_known": True,
        },
    )
    hits = {"copilot": 0, "oc": 0}

    def boom_c(*a, **k):
        hits["copilot"] += 1
        raise AssertionError("ear must not fetch copilot")

    def boom_o(*a, **k):
        hits["oc"] += 1
        raise AssertionError("ear must not fetch opencode")

    monkeypatch.setattr(bobreport, "fetch_live_copilot_pool", boom_c)
    monkeypatch.setattr(bobreport, "read_local_opencode_fuel_doc", boom_o)
    monkeypatch.setattr(bobreport, "post_report_json", lambda payload, url=None: 204)
    monkeypatch.setattr(
        bobreport,
        "resolve_fuel_report_target",
        lambda url=None, env=None: {
            "ok": True,
            "url": "https://example.test/bob/v1/report",
            "host": "example.test",
            "path": "/bob/v1/report",
            "source": "test",
            "error": None,
        },
    )
    monkeypatch.setattr(bobreport, "fetch_live_xai_weekly", lambda: None)
    monkeypatch.setattr(
        bobreport, "enrich_peer_keep_last_good_xai_weekly", lambda peer, error=None: dict(peer)
    )
    code = bobreport.publish_local_peer_fuel(home, "flamingo", force=True, now=1_700_000_000.0)
    assert code == 204
    assert hits["copilot"] == 0
    assert hits["oc"] == 0
    diag = bobreport.last_fuel_publish_diag()
    assert diag.get("copilot_acquisition") == "jeeves-fleet"
    assert "copilot" not in (diag.get("payload_keys") or [])
