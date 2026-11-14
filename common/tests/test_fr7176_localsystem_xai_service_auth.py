"""FR #7176: LocalSystem ear must fetch xAI weekly (no system-profile-skipped).

Si: if the service runs as SYSTEM and cannot fetch as SYSTEM, that is a bug.
Credentials are configured for the service (service home / stamped path /
BOB_GROK_AUTH_PATH), never interactive-profile-only. Missing/stale pools fail.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import bobreport
import bobstat


def _auth_doc(key: str = "FAKE_SESSION_KEY_7176") -> str:
    return json.dumps(
        {
            "issuer::client": {
                "key": key,
                "email": "fleet7176@example.com",
                "expires_at": "2099-01-01T00:00:00Z",
            }
        }
    )


def _billing_doc(used_pct: float = 28.0) -> dict:
    return {
        "config": {
            "currentPeriod": {
                "type": "USAGE_PERIOD_TYPE_WEEKLY",
                "end": "2026-11-21T12:00:00Z",
            },
            "creditUsagePercent": used_pct,
        }
    }


def _system_env(monkeypatch, tmp_path: Path, *, install: Path) -> Path:
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
    monkeypatch.delenv("BOB_WEEKLY_FORCE_SYSTEM_PROFILE", raising=False)
    monkeypatch.setattr(bobreport, "_is_local_system_process", lambda: True)
    monkeypatch.setattr(bobreport, "_console_user_account", lambda: None)
    monkeypatch.setattr(bobreport, "_last_logged_on_account", lambda: None)
    monkeypatch.setattr(bobreport, "_read_interactive_user_home_stamp", lambda: None)
    return sys_home


def test_fr7176_localsystem_never_system_profile_skipped(monkeypatch, tmp_path: Path):
    install = tmp_path / "bob"
    _system_env(monkeypatch, tmp_path, install=install)
    path, ident = bobreport.xai_weekly_auth_path()
    assert path is None
    assert ident == "auth-unresolved"
    assert ident != "system-profile-skipped"
    path2, ident2 = bobreport.xai_weekly_log_candidate()
    assert path2 is None
    assert ident2 == "auth-unresolved"


def test_fr7176_service_home_auth_used_under_localsystem(monkeypatch, tmp_path: Path):
    install = tmp_path / "bob"
    _system_env(monkeypatch, tmp_path, install=install)
    auth = install / "home" / ".grok" / "auth.json"
    auth.parent.mkdir(parents=True)
    auth.write_text(_auth_doc(), encoding="utf-8")

    path, ident = bobreport.xai_weekly_auth_path()
    assert ident == "service-auth"
    assert path == auth
    stamp = bobreport.grok_auth_path_stamp_path()
    assert stamp is not None and stamp.is_file()
    stamped = stamp.read_text(encoding="utf-8")
    assert str(auth) in stamped
    assert "FAKE_" not in stamped


def test_fr7176_stale_stamp_falls_through_to_service_auth(
    monkeypatch, tmp_path: Path
):
    """Missing stamped path must not shadow service-home auth.json (MRB #7188)."""
    install = tmp_path / "bob"
    _system_env(monkeypatch, tmp_path, install=install)
    stamp = install / "run" / bobreport.GROK_AUTH_PATH_STAMP_NAME
    stamp.write_text(str(tmp_path / "gone" / "auth.json") + "\n", encoding="utf-8")
    auth = install / "home" / ".grok" / "auth.json"
    auth.parent.mkdir(parents=True)
    auth.write_text(_auth_doc(), encoding="utf-8")

    path, ident = bobreport.xai_weekly_auth_path()
    assert ident == "service-auth"
    assert path == auth


def test_fr7176_stamped_auth_survives_without_interactive_home(
    monkeypatch, tmp_path: Path
):
    install = tmp_path / "bob"
    _system_env(monkeypatch, tmp_path, install=install)
    user = tmp_path / "Users" / "FleetAdmin7176"
    auth = user / ".grok" / "auth.json"
    auth.parent.mkdir(parents=True)
    auth.write_text(_auth_doc("FAKE_STAMP_7176"), encoding="utf-8")
    stamp = install / "run" / bobreport.GROK_AUTH_PATH_STAMP_NAME
    stamp.write_text(str(auth) + "\n", encoding="utf-8")

    path, ident = bobreport.xai_weekly_auth_path()
    assert ident == "stamped-auth"
    assert path == auth


def test_fr7176_localsystem_live_fetch_advances_fetched_at(
    monkeypatch, tmp_path: Path, isolated_xai_selection
):
    """Two publish cycles under SYSTEM: real numbers + advancing fetched_at."""
    install = tmp_path / "bob"
    _system_env(monkeypatch, tmp_path, install=install)
    auth = install / "home" / ".grok" / "auth.json"
    auth.parent.mkdir(parents=True)
    auth.write_text(_auth_doc(), encoding="utf-8")

    home = install / "home"
    mid = "marchhare"
    bobstat.write_peer(
        home,
        {
            "ok": True,
            "id": mid,
            "online": True,
            "status": "operational",
            "weekly": None,
            "weekly_known": False,
        },
    )

    clocks = [
        datetime(2026, 11, 14, 13, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 11, 14, 13, 5, 0, tzinfo=timezone.utc),
    ]
    used = [40.0, 41.0]
    call_i = {"n": 0}
    posted: list[dict] = []

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        url = req.get_full_url()
        if "billing" in url:
            i = call_i["n"]
            call_i["n"] = i + 1
            body = json.dumps(_billing_doc(used[i])).encode("utf-8")

            class Resp:
                status = 200

                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False

                def read(self):
                    return body

            return Resp()
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

    # Two fetches at least one interval apart: real numbers + advancing fetched_at.
    with mock.patch("urllib.request.urlopen", fake_urlopen):
        r1 = bobreport.fetch_live_xai_weekly(now=clocks[0])
        r2 = bobreport.fetch_live_xai_weekly(now=clocks[1])
    assert r1 is not None and r2 is not None
    assert r1["weekly_known"] is True and r2["weekly_known"] is True
    assert r1["remaining_pct"] == 60
    assert r2["remaining_pct"] == 59
    assert r1["fetched_at"] != r2["fetched_at"]
    assert r1["fetched_at"] < r2["fetched_at"]
    assert bobreport._last_xai_acquisition.get("identity") == "live-billing"
    assert bobreport._last_xai_acquisition.get("auth_identity") in (
        "service-auth",
        "stamped-auth",
    )
    assert "system-profile-skipped" not in str(bobreport._last_xai_acquisition)

    # Publish path under SYSTEM uses service auth (no skip).
    call_i["n"] = 0
    with mock.patch("urllib.request.urlopen", fake_urlopen):
        code = bobreport.publish_local_peer_fuel(
            home, mid, force=True, url="https://example.test/bob/v1/report"
        )
    assert code == 204
    assert posted, "expected digest POST"
    body = posted[0]
    assert body.get("weekly") == 60
    meter = body.get("xai_weekly") or {}
    assert meter.get("fresh") is True
    assert meter.get("fetched_at")
    assert bobreport._last_fuel_publish_diag.get("acquisition") == "live-billing"
    assert bobreport._last_fuel_publish_diag.get("acquisition") != "system-profile-skipped"


def test_fr7176_spoofed_systemprofile_without_localsystem_still_skipped(
    monkeypatch, tmp_path: Path, isolated_xai_selection
):
    """Unit-test spoof (USERNAME=tester) may still skip; live SYSTEM must not."""
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "systemprofile"))
    (tmp_path / "systemprofile").mkdir(exist_ok=True)
    monkeypatch.setenv("USERNAME", "tester")
    monkeypatch.delenv("BOB_GROK_AUTH_PATH", raising=False)
    monkeypatch.delenv("BOB_GROK_WEEKLY_USER_HOME", raising=False)
    monkeypatch.setattr(bobreport, "_is_local_system_process", lambda: False)
    path, ident = bobreport.xai_weekly_auth_path()
    assert path is None
    assert ident == "system-profile-skipped"
