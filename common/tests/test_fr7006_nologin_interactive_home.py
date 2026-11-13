"""FR #7006: LocalSystem xAI home when no one is logged on (CIM UserName empty)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import bobreport


def test_fr7006_last_logged_on_when_cim_empty(monkeypatch, tmp_path: Path):
    user = "FleetAdmin7006"
    home = tmp_path / "Users" / user
    home.mkdir(parents=True)
    (home / ".grok").mkdir()
    auth = home / ".grok" / "auth.json"
    auth.write_text(json.dumps({"key": "FAKE_SESSION_KEY_7006"}), encoding="utf-8")

    monkeypatch.setenv("SystemDrive", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "systemprofile"))
    (tmp_path / "systemprofile").mkdir(exist_ok=True)
    monkeypatch.setenv("USERNAME", "SYSTEM")
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(tmp_path / "bob"))
    (tmp_path / "bob" / "run").mkdir(parents=True)
    monkeypatch.delenv("BOB_GROK_WEEKLY_USER_HOME", raising=False)
    monkeypatch.delenv("BOB_GROK_AUTH_PATH", raising=False)
    monkeypatch.setattr(bobreport, "_is_local_system_process", lambda: True)
    monkeypatch.setattr(
        bobreport.subprocess,
        "run",
        mock.Mock(return_value=mock.Mock(returncode=0, stdout="", stderr="")),
    )
    monkeypatch.setattr(
        bobreport, "_last_logged_on_account", lambda: f"WONDERLAND\\{user}"
    )

    found = bobreport._interactive_grok_user_home()
    assert found == home
    path, ident = bobreport.xai_weekly_auth_path()
    assert ident == "interactive-auth"
    assert path == auth
    stamp = bobreport.interactive_user_home_stamp_path()
    assert stamp is not None and stamp.is_file()
    assert user in stamp.read_text(encoding="utf-8")
    assert "FAKE_" not in stamp.read_text(encoding="utf-8")


def test_fr7006_persisted_stamp_when_cim_and_logon_empty(monkeypatch, tmp_path: Path):
    user = "ParkedAdmin7006"
    home = tmp_path / "Users" / user
    home.mkdir(parents=True)
    install = tmp_path / "bob"
    run = install / "run"
    run.mkdir(parents=True)
    (run / bobreport.INTERACTIVE_HOME_STAMP_NAME).write_text(
        str(home) + "\n", encoding="utf-8"
    )

    monkeypatch.setenv("SystemDrive", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "systemprofile"))
    (tmp_path / "systemprofile").mkdir(exist_ok=True)
    monkeypatch.setenv("USERNAME", "SYSTEM")
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(install))
    monkeypatch.delenv("BOB_GROK_WEEKLY_USER_HOME", raising=False)
    monkeypatch.delenv("BOB_GROK_AUTH_PATH", raising=False)
    monkeypatch.setattr(bobreport, "_is_local_system_process", lambda: True)
    monkeypatch.setattr(
        bobreport.subprocess,
        "run",
        mock.Mock(return_value=mock.Mock(returncode=0, stdout="", stderr="")),
    )
    monkeypatch.setattr(bobreport, "_last_logged_on_account", lambda: None)

    found = bobreport._interactive_grok_user_home()
    assert found == home
    path, ident = bobreport.xai_weekly_auth_path()
    assert ident == "interactive-auth"
    assert path == home / ".grok" / "auth.json"


def test_fr7006_still_skips_when_no_logon_no_stamp(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SystemDrive", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "systemprofile"))
    (tmp_path / "systemprofile").mkdir(exist_ok=True)
    monkeypatch.setenv("USERNAME", "SYSTEM")
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(tmp_path / "bob"))
    (tmp_path / "bob" / "run").mkdir(parents=True)
    monkeypatch.delenv("BOB_GROK_WEEKLY_USER_HOME", raising=False)
    monkeypatch.delenv("BOB_GROK_AUTH_PATH", raising=False)
    monkeypatch.setattr(bobreport, "_is_local_system_process", lambda: True)
    monkeypatch.setattr(
        bobreport.subprocess,
        "run",
        mock.Mock(return_value=mock.Mock(returncode=0, stdout="", stderr="")),
    )
    monkeypatch.setattr(bobreport, "_last_logged_on_account", lambda: None)

    assert bobreport._interactive_grok_user_home() is None
    path, ident = bobreport.xai_weekly_auth_path()
    assert path is None
    assert ident == "system-profile-skipped"
