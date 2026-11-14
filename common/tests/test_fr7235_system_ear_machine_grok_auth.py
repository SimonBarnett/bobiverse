"""FR #7235: SYSTEM ear reads the machine Grok auth.json every fetch (no stale copy)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import bobreport
import urllib.error


def _auth_doc(key: str) -> str:
    return json.dumps(
        {
            "issuer::client": {
                "key": key,
                "email": "fleet7235@example.com",
                "expires_at": "2099-01-01T00:00:00Z",
            }
        }
    )


def _system_env(monkeypatch, tmp_path: Path, *, install: Path) -> None:
    sys_home = tmp_path / "systemprofile"
    sys_home.mkdir(exist_ok=True)
    monkeypatch.setenv("USERPROFILE", str(sys_home))
    monkeypatch.setenv("USERNAME", "SYSTEM")
    monkeypatch.setenv("SystemDrive", str(tmp_path))
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(install))
    (install / "run").mkdir(parents=True, exist_ok=True)
    (install / "home").mkdir(parents=True, exist_ok=True)
    monkeypatch.delenv("BOB_GROK_AUTH_PATH", raising=False)
    monkeypatch.delenv("GROK_AUTH_PATH", raising=False)
    monkeypatch.delenv("GROK_HOME", raising=False)
    monkeypatch.delenv("BOB_GROK_WEEKLY_USER_HOME", raising=False)
    monkeypatch.delenv("BOB_WEEKLY_LOG", raising=False)
    monkeypatch.setattr(bobreport, "_is_local_system_process", lambda: True)


def _billing_ok(used_pct: float) -> object:
    body = json.dumps(
        {
            "config": {
                "currentPeriod": {
                    "type": "USAGE_PERIOD_TYPE_WEEKLY",
                    "end": "2026-11-21T12:00:00Z",
                },
                "creditUsagePercent": used_pct,
            }
        }
    ).encode("utf-8")

    class Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return body

    return Resp()


def test_fr7235_interactive_wins_over_stale_service_copy_and_stamp(
    monkeypatch, tmp_path: Path
):
    install = tmp_path / "bob"
    _system_env(monkeypatch, tmp_path, install=install)
    stale = install / "home" / ".grok" / "auth.json"
    stale.parent.mkdir(parents=True)
    stale.write_text(_auth_doc("FAKE_STALE_SERVICE_COPY"), encoding="utf-8")
    stamp = install / "run" / bobreport.GROK_AUTH_PATH_STAMP_NAME
    stamp.write_text(str(stale) + "\n", encoding="utf-8")
    user = tmp_path / "Users" / "FleetAdmin7235"
    live = user / ".grok" / "auth.json"
    live.parent.mkdir(parents=True)
    live.write_text(_auth_doc("FAKE_LIVE_MACHINE_KEY"), encoding="utf-8")
    monkeypatch.setattr(bobreport, "_console_user_account", lambda: r"WONDERLAND\FleetAdmin7235")
    monkeypatch.setattr(bobreport, "_last_logged_on_account", lambda: None)

    path, ident = bobreport.xai_weekly_auth_path()
    assert ident == "interactive-auth"
    assert path == live
    assert path != stale


def test_fr7235_reread_machine_store_after_seat_refresh(
    monkeypatch, tmp_path: Path
):
    install = tmp_path / "bob"
    _system_env(monkeypatch, tmp_path, install=install)
    user = tmp_path / "Users" / "FleetAdmin7235"
    live = user / ".grok" / "auth.json"
    live.parent.mkdir(parents=True)
    live.write_text(_auth_doc("FAKE_KEY_ONE"), encoding="utf-8")
    monkeypatch.setattr(bobreport, "_console_user_account", lambda: r"WONDERLAND\FleetAdmin7235")
    monkeypatch.setattr(bobreport, "_last_logged_on_account", lambda: None)
    keys_seen: list[str] = []

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        hdr = req.get_header("Authorization") or ""
        keys_seen.append(hdr.replace("Bearer ", ""))
        return _billing_ok(10.0 if len(keys_seen) == 1 else 12.0)

    clocks = [
        datetime(2026, 11, 14, 15, 0, tzinfo=timezone.utc),
        datetime(2026, 11, 14, 15, 5, tzinfo=timezone.utc),
    ]
    with mock.patch("urllib.request.urlopen", fake_urlopen):
        r1 = bobreport.fetch_live_xai_weekly(now=clocks[0])
        live.write_text(_auth_doc("FAKE_KEY_TWO"), encoding="utf-8")
        r2 = bobreport.fetch_live_xai_weekly(now=clocks[1])
    assert r1 is not None and r2 is not None
    assert r1["fetched_at"] < r2["fetched_at"]
    assert keys_seen == ["FAKE_KEY_ONE", "FAKE_KEY_TWO"]
    assert bobreport._last_xai_acquisition.get("auth_identity") == "interactive-auth"
    assert bobreport._last_xai_acquisition.get("auth_path") == str(live)
    blob = json.dumps(bobreport._last_xai_acquisition)
    assert "FAKE_KEY" not in blob


def test_fr7235_expired_names_file_not_contents(monkeypatch, tmp_path: Path):
    install = tmp_path / "bob"
    _system_env(monkeypatch, tmp_path, install=install)
    user = tmp_path / "Users" / "FleetAdmin7235"
    live = user / ".grok" / "auth.json"
    live.parent.mkdir(parents=True)
    live.write_text(_auth_doc("FAKE_EXPIRED_SESSION"), encoding="utf-8")
    monkeypatch.setattr(bobreport, "_console_user_account", lambda: r"WONDERLAND\FleetAdmin7235")
    monkeypatch.setattr(bobreport, "_last_logged_on_account", lambda: None)

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        raise urllib.error.HTTPError(req.get_full_url(), 401, "denied", hdrs=None, fp=None)

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        got = bobreport.fetch_live_xai_weekly(
            now=datetime(2026, 11, 14, 15, 0, tzinfo=timezone.utc)
        )
    assert got is None
    acq = bobreport._last_xai_acquisition
    assert acq.get("error") == bobreport.XAI_GROK_LOGIN_EXPIRED
    assert acq.get("auth_path") == str(live)
    assert "FAKE_EXPIRED" not in json.dumps(acq)
