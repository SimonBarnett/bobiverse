"""FR #8507: missing interactive auth.json must not shadow service/stamped auth.

Redqueen filed ear-pool-stale with last_fetch_error=auth-file-missing when
LocalSystem resolved an interactive user home that had no ``.grok/auth.json``.
That path was returned (and stamped) without ``is_file``, so service-home never
ran and the weekly pool stayed stale.
"""
from __future__ import annotations

import json
from pathlib import Path

import bobreport


def _auth_doc(key: str = "FAKE_SESSION_KEY_8507") -> str:
    return json.dumps(
        {
            "issuer::client": {
                "key": key,
                "email": "fleet8507@example.com",
                "expires_at": "2099-01-01T00:00:00Z",
            }
        }
    )


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
    monkeypatch.setattr(bobreport, "_is_local_system_process", lambda: True)
    return sys_home


def test_fr8507_missing_interactive_falls_through_to_service_auth(
    monkeypatch, tmp_path: Path
):
    install = tmp_path / "bob"
    _system_env(monkeypatch, tmp_path, install=install)
    user = tmp_path / "Users" / "FleetAdmin8507"
    # Interactive home exists but has no auth.json (redqueen class).
    (user / ".grok").mkdir(parents=True)
    monkeypatch.setattr(
        bobreport, "_console_user_account", lambda: r"WONDERLAND\FleetAdmin8507"
    )
    monkeypatch.setattr(bobreport, "_last_logged_on_account", lambda: None)
    auth = install / "home" / ".grok" / "auth.json"
    auth.parent.mkdir(parents=True)
    auth.write_text(_auth_doc(), encoding="utf-8")

    path, ident = bobreport.xai_weekly_auth_path()
    assert ident == "service-auth"
    assert path == auth
    # Must not stamp the missing interactive path.
    stamp = bobreport.grok_auth_path_stamp_path()
    assert stamp is not None and stamp.is_file()
    stamped = stamp.read_text(encoding="utf-8")
    assert str(auth) in stamped
    assert "FleetAdmin8507" not in stamped
    assert "FAKE_" not in stamped


def test_fr8507_missing_interactive_no_service_is_auth_unresolved(
    monkeypatch, tmp_path: Path
):
    install = tmp_path / "bob"
    _system_env(monkeypatch, tmp_path, install=install)
    user = tmp_path / "Users" / "FleetAdmin8507"
    (user / ".grok").mkdir(parents=True)
    monkeypatch.setattr(
        bobreport, "_console_user_account", lambda: r"WONDERLAND\FleetAdmin8507"
    )
    monkeypatch.setattr(bobreport, "_last_logged_on_account", lambda: None)

    path, ident = bobreport.xai_weekly_auth_path()
    assert path is None
    assert ident == "auth-unresolved"
    acq_path, acq_ident = bobreport.xai_weekly_auth_path()
    assert acq_path is None and acq_ident == "auth-unresolved"
    # fetch must not report auth-file-missing for a path that never existed
    got = bobreport.fetch_live_xai_weekly()
    assert got is None
    err = (bobreport._last_xai_acquisition or {}).get("error")
    assert err == "auth-unresolved"
    assert err != "auth-file-missing"


def test_fr8507_write_stamp_skips_missing_auth_file(monkeypatch, tmp_path: Path):
    install = tmp_path / "bob"
    _system_env(monkeypatch, tmp_path, install=install)
    missing = tmp_path / "Users" / "Nobody" / ".grok" / "auth.json"
    bobreport._write_grok_auth_path_stamp(missing)
    stamp = bobreport.grok_auth_path_stamp_path()
    assert stamp is not None
    assert not stamp.is_file()
