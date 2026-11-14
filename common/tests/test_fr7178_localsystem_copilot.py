"""FR #7178: LocalSystem ear fetches and publishes GitHub Copilot usage.

Si: if the service runs as SYSTEM and cannot fetch as SYSTEM, that is a bug.
Missing pools = fail. Stale pools = fail. Publish remaining / entitlement /
quota_reset_date (reset_at), or an explicit error — never omit the pool.
"""
from __future__ import annotations

from pathlib import Path

import bobreport
import bobstat
import copilot_dispatch as cd


SAMPLE_USER = {
    "copilot_plan": "business",
    "quota_reset_date_utc": "2026-12-01T00:00:00.000Z",
    "quota_snapshots": {
        "premium_interactions": {
            "credits_used": 10,
            "remaining": 40,
            "entitlement": 50,
            "percent_remaining": 80.0,
            "unlimited": False,
            "overage_permitted": False,
        }
    },
}


def _system_env(monkeypatch, tmp_path: Path, *, install: Path) -> None:
    sys_home = tmp_path / "systemprofile"
    sys_home.mkdir(exist_ok=True)
    monkeypatch.setenv("USERPROFILE", str(sys_home))
    monkeypatch.setenv("LOCALAPPDATA", str(sys_home / "AppData" / "Local"))
    (sys_home / "AppData" / "Local").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("USERNAME", "SYSTEM")
    monkeypatch.setenv("SystemDrive", str(tmp_path))
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(install))
    # Keep digest helpers on the test home (FR #6523 isolated suite).
    monkeypatch.setenv("BOBIVERSE_BUILD_SUITE", "1")
    monkeypatch.setenv("BOB_DIGEST_HOME", str(install / "home"))
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("BOB_COPILOT_OBSERVE", raising=False)
    monkeypatch.delenv("BOB_CONFIG_DIR", raising=False)
    monkeypatch.setattr(bobreport, "_is_local_system_process", lambda: True)
    monkeypatch.setattr(bobreport.sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        bobreport.sys,
        "executable",
        str(install / "scripts" / "bob-ear.exe"),
        raising=False,
    )
    (install / "scripts").mkdir(parents=True, exist_ok=True)
    (install / "scripts" / "bob-ear.exe").write_bytes(b"MZ")
    (install / "config").mkdir(parents=True, exist_ok=True)
    (install / "home").mkdir(parents=True, exist_ok=True)


def test_fr7178_install_token_resolves_under_localsystem(monkeypatch, tmp_path: Path):
    install = tmp_path / "bob"
    _system_env(monkeypatch, tmp_path, install=install)
    token_path = install / "config" / "github.token"
    token_path.write_text("FAKE_GH_TOKEN_7178", encoding="utf-8")
    tok, src = bobreport.resolve_github_token_for_ear()
    assert tok == "FAKE_GH_TOKEN_7178"
    assert src == "file:github.token"
    assert "FAKE_GH_TOKEN_7178" not in src


def test_fr7178_fetch_advances_fetched_at_and_publishes_fields(
    monkeypatch, tmp_path: Path
):
    install = tmp_path / "bob"
    _system_env(monkeypatch, tmp_path, install=install)
    home = install / "home"
    (install / "config" / "github.token").write_text("FAKE_GH_TOKEN_7178", encoding="utf-8")

    pool1 = bobreport.fetch_live_copilot_pool(
        home, now=1_000.0, fetch_user=lambda: SAMPLE_USER
    )
    assert pool1["remaining"] == 40
    assert pool1["entitlement"] == 50
    assert "2026-12-01" in str(pool1["reset_at"])
    assert pool1["fetched_at"]
    assert pool1["state"] == "ok"
    fa1 = pool1["fetched_at"]

    pool2 = bobreport.fetch_live_copilot_pool(
        home, now=1_000.0 + cd.CACHE_S + 10.0, fetch_user=lambda: SAMPLE_USER
    )
    assert pool2["fetched_at"]
    assert pool2["fetched_at"] != fa1
    assert pool2["remaining"] == 40
    acq = bobreport.last_copilot_acquisition()
    assert acq.get("kind") == "ok"
    assert acq.get("remaining") == 40
    assert acq.get("entitlement") == 50


def test_fr7178_missing_token_publishes_explicit_error_never_omits(
    monkeypatch, tmp_path: Path
):
    install = tmp_path / "bob"
    _system_env(monkeypatch, tmp_path, install=install)
    home = install / "home"
    # No github.token, no env token.
    pool = bobreport.fetch_live_copilot_pool(home, now=50.0)
    assert isinstance(pool, dict)
    assert pool.get("state") == "unknown"
    assert pool.get("last_error") in ("no_token", "unread")
    assert "remaining" in pool
    assert "entitlement" in pool
    assert "reset_at" in pool
    assert pool.get("fetched_at") in ("", None) or pool.get("state") == "unknown"
    acq = bobreport.last_copilot_acquisition()
    assert acq.get("kind") in ("missing_token", "unread")
    assert acq.get("error") in ("no_token", "unread")


def test_fr7178_publish_payload_always_includes_copilot(monkeypatch, tmp_path: Path):
    install = tmp_path / "bob"
    _system_env(monkeypatch, tmp_path, install=install)
    home = install / "home"
    mid = "marchhare"
    bobstat.write_peer(
        home,
        {
            "id": mid,
            "ok": True,
            "online": True,
            "status": "operational",
            "weekly": 10,
            "weekly_known": True,
        },
    )
    monkeypatch.setattr(
        bobreport,
        "fetch_live_copilot_pool",
        lambda h, now=None, fetch_user=None: cd.ensure_public_pool(
            {
                "remaining": 12,
                "entitlement": 50,
                "reset_at": "2026-12-01T00:00:00.000Z",
                "fetched_at": "2026-11-14T12:00:00Z",
                "state": "ok",
                "source": "copilot_internal/user",
            }
        ),
    )
    monkeypatch.setattr(
        bobreport,
        "last_copilot_acquisition",
        lambda: {"kind": "ok", "source": "file:github.token"},
    )
    monkeypatch.setattr(bobreport, "post_report_json", lambda payload, url=None: 204)
    monkeypatch.setattr(
        bobreport,
        "resolve_fuel_report_target",
        lambda url=None, env=None: {
            "ok": True,
            "url": "https://bob.ntsa.uk/bob/v1/report",
            "host": "bob.ntsa.uk",
            "path": "/bob/v1/report",
            "source": "test",
            "error": None,
        },
    )
    # Avoid xAI/OpenCode side effects.
    monkeypatch.setattr(bobreport, "fetch_live_xai_weekly", lambda: None)
    monkeypatch.setattr(
        bobreport,
        "enrich_peer_keep_last_good_xai_weekly",
        lambda peer, error=None: dict(peer),
    )
    monkeypatch.setattr(
        bobreport, "read_local_opencode_fuel_doc", lambda force=False: {}
    )
    monkeypatch.setattr(bobreport, "read_grok_account_label", lambda: ("none", None))
    monkeypatch.setattr(bobstat, "refresh_peer_cursor_remaining", lambda *a, **k: None)

    code = bobreport.publish_local_peer_fuel(home, mid, force=True, now=1_700_000_000.0)
    assert code == 204
    diag = bobreport.last_fuel_publish_diag()
    assert "copilot" in (diag.get("payload_keys") or [])
    assert diag.get("copilot_acquisition") == "ok"
    line = bobreport.format_fuel_publish_diag(diag)
    assert "copilot_acquisition=ok" in line


def test_fr7178_merge_promotes_fresher_copilot_to_digest_top_level(
    monkeypatch, tmp_path: Path
):
    home = tmp_path / "digest"
    home.mkdir()
    monkeypatch.setenv("BOBIVERSE_BUILD_SUITE", "1")
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    doc = {
        "v": 1,
        "ts": "2026-11-01T00:00:00Z",
        "machines": {"marchhare": {"id": "marchhare", "online": True}},
    }
    bobreport._apply_merge_payload(
        doc,
        "marchhare",
        {
            "op": "merge",
            "machine": "marchhare",
            "online": True,
            "status": "operational",
            "copilot": {
                "remaining": 9,
                "entitlement": 50,
                "reset_at": "2026-12-01T00:00:00.000Z",
                "fetched_at": "2026-11-14T13:00:00Z",
                "state": "ok",
                "source": "copilot_internal/user",
            },
        },
    )
    assert doc["machines"]["marchhare"]["copilot"]["remaining"] == 9
    assert doc["copilot"]["remaining"] == 9
    assert doc["copilot"]["entitlement"] == 50
    bobreport.save_digest(home, doc)
    # Sticky top-level survives load even when ChanServ roster strips machines.
    loaded = bobreport.load_digest(home)
    assert loaded["copilot"]["remaining"] == 9
    obj = bobreport.build_digest_object(home, "Jeeves")
    assert obj["copilot"]["remaining"] == 9
    assert obj["copilot"]["entitlement"] == 50
    assert "2026-12-01" in str(obj["copilot"]["reset_at"])


def test_fr7178_digest_never_omits_copilot_when_unread(monkeypatch, tmp_path: Path):
    home = tmp_path / "digest"
    home.mkdir()
    monkeypatch.setenv("BOBIVERSE_BUILD_SUITE", "1")
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    bobreport.save_digest(home, bobreport.empty_digest())
    obj = bobreport.build_digest_object(home, "Jeeves")
    assert "copilot" in obj
    assert isinstance(obj["copilot"], dict)
    assert "remaining" in obj["copilot"]
    assert "entitlement" in obj["copilot"]
    assert "reset_at" in obj["copilot"]
    assert obj["copilot"].get("state") in ("unknown", "ok", "exhausted")
