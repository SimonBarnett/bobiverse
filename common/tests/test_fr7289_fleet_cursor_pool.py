"""FR #7289: Jeeves fleet Cursor pool; ears stop fetching Cursor."""
from __future__ import annotations

from pathlib import Path

import bobreport
import fleet_pool_fetch as fp


def test_fr7289_cursor_pool_id_and_60s():
    assert fp.POOL_CURSOR == "cursor"
    assert fp.FLEET_POOL_FETCH_S == 60.0
    assert "cursor" in fp.public_fleet_section({fp.POOL_CURSOR: {"id": "cursor", "remaining": 1}})


def test_fr7289_success_stamps_fetched_at(tmp_path: Path):
    home = tmp_path / "digest"
    home.mkdir()
    bobreport.save_digest(home, bobreport.empty_digest())
    t0 = 1_700_000_000.0

    def copilot(_h, now):
        return {
            "id": "copilot",
            "remaining": 1,
            "fetched_at": fp.iso_utc(now),
            "error": None,
            "source": "copilot_internal/user",
            "fresh": True,
        }

    def oc(_h, now):
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
                "remaining": 1,
                "fetched_at": iso,
                "error": None,
                "source": "go-zen-usage",
                "fresh": True,
            },
        }

    def cursor(_h, now):
        return {
            "id": "cursor",
            "remaining": 44,
            "fetched_at": fp.iso_utc(now),
            "last_attempt_at": fp.iso_utc(now),
            "error": None,
            "source": "credman:Bobiverse/CursorAccess",
            "fresh": True,
        }

    a = fp.tick_fleet_pools(
        home,
        now=t0,
        force=True,
        fetch_copilot=copilot,
        fetch_opencode=oc,
        fetch_cursor=cursor,
    )
    b = fp.tick_fleet_pools(
        home,
        now=t0 + 60.0,
        force=True,
        fetch_copilot=copilot,
        fetch_opencode=oc,
        fetch_cursor=cursor,
    )
    assert a["cursor"]["fetched_at"] != b["cursor"]["fetched_at"]
    assert a["cursor"]["remaining"] == 44
    pub = bobreport.build_digest_object(home, "jeeves")
    assert pub["fleet_pools"]["cursor"]["fetched_at"] == b["cursor"]["fetched_at"]
    blob = str(pub)
    assert "Bearer" not in blob
    assert "FAKESECRET" not in blob.upper()


def test_fr7289_failure_keeps_last_value(tmp_path: Path):
    home = tmp_path / "digest"
    home.mkdir()
    bobreport.save_digest(home, bobreport.empty_digest())
    t0 = 1_700_000_000.0
    good = fp.iso_utc(t0)

    def copilot(_h, now):
        return {
            "id": "copilot",
            "remaining": 1,
            "fetched_at": fp.iso_utc(now),
            "error": None,
            "source": "x",
            "fresh": True,
        }

    def oc(_h, now):
        iso = fp.iso_utc(now)
        return {
            "opencode-free": {
                "id": "opencode-free",
                "remaining": 1,
                "fetched_at": iso,
                "error": None,
                "source": "x",
                "fresh": True,
            },
            "opencode-go": {
                "id": "opencode-go",
                "remaining": 1,
                "fetched_at": iso,
                "error": None,
                "source": "x",
                "fresh": True,
            },
        }

    def cursor_ok(_h, now):
        return {
            "id": "cursor",
            "remaining": 9,
            "fetched_at": fp.iso_utc(now),
            "error": None,
            "source": "credman:Bobiverse/CursorAccess",
            "fresh": True,
        }

    fp.tick_fleet_pools(
        home,
        now=t0,
        force=True,
        fetch_copilot=copilot,
        fetch_opencode=oc,
        fetch_cursor=cursor_ok,
    )

    def cursor_fail(_h, now):
        raise RuntimeError("provider-http-401")

    out = fp.tick_fleet_pools(
        home,
        now=t0 + 60.0,
        force=True,
        fetch_copilot=copilot,
        fetch_opencode=oc,
        fetch_cursor=cursor_fail,
    )
    assert out["cursor"]["fetched_at"] == good
    assert out["cursor"]["remaining"] == 9
    assert out["cursor"]["fresh"] is False
    assert out["cursor"]["error"]
    assert out["cursor"]["last_attempt_at"] == fp.iso_utc(t0 + 60.0)


def test_fr7289_ear_does_not_fetch_cursor(monkeypatch, tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    import bobstat as bs

    bs.write_peer(
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
    hits = {"cursor": 0}

    def boom(*a, **k):
        hits["cursor"] += 1
        raise AssertionError("ear must not fetch cursor")

    monkeypatch.setattr(bs, "load_cursor_usage_doc", boom)
    monkeypatch.setattr(bs, "refresh_peer_cursor_remaining", boom)
    monkeypatch.setattr(bobreport, "fetch_live_copilot_pool", lambda *a, **k: None)
    monkeypatch.setattr(bobreport, "read_local_opencode_fuel_doc", lambda *a, **k: None)
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
    assert hits["cursor"] == 0
    diag = bobreport.last_fuel_publish_diag()
    assert diag.get("cursor_acquisition") == "jeeves-fleet"


def test_fr7289_no_key_source_is_credman_tag_not_secret():
    row = fp.empty_meter(
        pool_id=fp.POOL_CURSOR,
        source="credman:Bobiverse/CursorAccess",
        error="no_key",
        now=1_700_000_000.0,
    )
    assert row["source"] == "credman:Bobiverse/CursorAccess"
    assert row["fetched_at"] is None
    assert "Bearer" not in str(row)


def test_fr7289_tray_reads_fleet_cursor():
    hover = Path(__file__).resolve().parents[2] / "bob" / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
    text = hover.read_text(encoding="utf-8")
    assert "fleet_pools" in text
    assert "cursor" in text.lower()
    assert "Get-BobPoolStaleAfterSec" in text
    assert "FR #7289" in text or "fleet_pools.cursor" in text or "fleet cursor" in text.lower()


def test_fr7289_cursor_remaining_from_period_auto():
    period = {"planUsage": {"autoPercentUsed": 25}}
    rem = fp.cursor_remaining_from_period(period)
    assert rem == 75
