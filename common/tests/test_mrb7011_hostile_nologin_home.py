"""MRB #7011 hostile pins for FR #7006 nologin interactive home."""
from __future__ import annotations

from pathlib import Path
from unittest import mock

import bobreport


def test_mrb7011_weekly_user_home_wins_over_last_logged_on(monkeypatch, tmp_path: Path):
    override = tmp_path / "nssm-home"
    override.mkdir()
    other = tmp_path / "Users" / "OtherAdmin"
    other.mkdir(parents=True)

    monkeypatch.setenv("SystemDrive", str(tmp_path))
    monkeypatch.setenv("BOB_GROK_WEEKLY_USER_HOME", str(override))
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(tmp_path / "bob"))
    (tmp_path / "bob" / "run").mkdir(parents=True)
    monkeypatch.setattr(bobreport, "_console_user_account", lambda: None)
    monkeypatch.setattr(bobreport, "_last_logged_on_account", lambda: r"WONDERLAND\OtherAdmin")

    assert bobreport._interactive_grok_user_home() == override


def test_mrb7011_service_account_last_logged_on_rejected(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SystemDrive", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "systemprofile"))
    (tmp_path / "systemprofile").mkdir(exist_ok=True)
    monkeypatch.setenv("USERNAME", "SYSTEM")
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(tmp_path / "bob"))
    (tmp_path / "bob" / "run").mkdir(parents=True)
    monkeypatch.delenv("BOB_GROK_WEEKLY_USER_HOME", raising=False)
    monkeypatch.setattr(bobreport, "_console_user_account", lambda: None)
    monkeypatch.setattr(bobreport, "_last_logged_on_account", lambda: r"NT AUTHORITY\SYSTEM")
    monkeypatch.setattr(bobreport, "_read_interactive_user_home_stamp", lambda: None)

    assert bobreport._interactive_grok_user_home() is None


def test_mrb7011_stamp_rejects_systemprofile(monkeypatch, tmp_path: Path):
    install = tmp_path / "bob"
    run = install / "run"
    run.mkdir(parents=True)
    sysprof = tmp_path / "Windows" / "systemprofile"
    sysprof.mkdir(parents=True)
    (run / bobreport.INTERACTIVE_HOME_STAMP_NAME).write_text(
        str(sysprof) + "\n", encoding="utf-8"
    )
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(install))
    monkeypatch.delenv("BOB_GROK_WEEKLY_USER_HOME", raising=False)
    monkeypatch.setattr(bobreport, "_console_user_account", lambda: None)
    monkeypatch.setattr(bobreport, "_last_logged_on_account", lambda: None)

    assert bobreport._read_interactive_user_home_stamp() is None
    assert bobreport._interactive_grok_user_home() is None
