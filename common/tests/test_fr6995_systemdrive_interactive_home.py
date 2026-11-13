"""FR #6995: LocalSystem interactive home must root SystemDrive (pathlib C: quirk).

After MSI 2.0.0, ircBob runs as LocalSystem without BOB_GROK_WEEKLY_USER_HOME.
Auto-resolve finds the console/explorer user but Path(SystemDrive)/Users/<user>
with SystemDrive=C: builds a drive-relative path (C:Users\\...) that is_dir()=False,
so acquisition stays system-profile-skipped and digest pools stay fresh=false.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import bobreport  # noqa: E402


def test_fr6995_system_drive_root_is_absolute(monkeypatch):
    monkeypatch.setenv("SystemDrive", "C:")
    root = bobreport._system_drive_root()
    assert root.is_absolute()
    assert str(root).replace("/", "\\").rstrip("\\").upper() == "C:"
    joined = root / "Users" / "Administrator"
    assert joined.is_absolute()
    text = str(joined).replace("/", "\\")
    assert text.upper().startswith("C:\\USERS\\")
    assert "C:Users" not in text


def test_fr6995_interactive_home_finds_users_dir_without_env_override(
    monkeypatch, tmp_path: Path
):
    """Post-install LocalSystem path: no BOB_GROK_WEEKLY_USER_HOME, explorer account."""
    user = "FleetAdmin6995"
    users_home = tmp_path / "Users" / user
    users_home.mkdir(parents=True)
    (users_home / ".grok").mkdir(parents=True)
    auth = users_home / ".grok" / "auth.json"
    # Shape only — never a real secret (FR #3304).
    auth.write_text(json.dumps({"key": "FAKE_SESSION_KEY_6995"}), encoding="utf-8")

    monkeypatch.setenv("SystemDrive", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "systemprofile"))
    (tmp_path / "systemprofile").mkdir(exist_ok=True)
    monkeypatch.setenv("USERNAME", "SYSTEM")
    monkeypatch.delenv("BOB_GROK_WEEKLY_USER_HOME", raising=False)
    monkeypatch.delenv("BOB_GROK_AUTH_PATH", raising=False)
    monkeypatch.delenv("BOB_WEEKLY_FORCE_SYSTEM_PROFILE", raising=False)
    monkeypatch.setattr(bobreport, "_is_local_system_process", lambda: True)

    fake = mock.Mock(
        return_value=mock.Mock(
            returncode=0, stdout=f"WONDERLAND\\{user}\n", stderr=""
        )
    )
    monkeypatch.setattr(subprocess, "run", fake)

    home = bobreport._interactive_grok_user_home()
    assert home == users_home
    assert fake.called

    path, identity = bobreport.xai_weekly_auth_path()
    assert identity == "interactive-auth"
    assert path == auth


def test_fr6995_auth_path_with_literal_c_systemdrive(monkeypatch, tmp_path: Path):
    """The live MSI bug: SystemDrive is exactly 'C:' (pathlib drive-relative trap)."""
    user = "Administrator"
    # Real C:\\Users\\Administrator usually exists on fleet boxes; pin via root helper.
    monkeypatch.setenv("SystemDrive", "C:")
    monkeypatch.setenv("USERPROFILE", r"C:\Windows\system32\config\systemprofile")
    monkeypatch.setenv("USERNAME", "SYSTEM")
    monkeypatch.delenv("BOB_GROK_WEEKLY_USER_HOME", raising=False)
    monkeypatch.delenv("BOB_GROK_AUTH_PATH", raising=False)
    monkeypatch.setattr(bobreport, "_is_local_system_process", lambda: True)

    fake = mock.Mock(
        return_value=mock.Mock(
            returncode=0, stdout=f"WONDERLAND\\{user}\n", stderr=""
        )
    )
    monkeypatch.setattr(subprocess, "run", fake)

    home = bobreport._interactive_grok_user_home()
    assert home is not None
    assert home == Path(r"C:\Users\Administrator")
    assert home.is_dir()
    path, identity = bobreport.xai_weekly_auth_path()
    assert identity == "interactive-auth"
    assert path == home / ".grok" / "auth.json"


def test_fr6995_auth_skipped_when_users_dir_missing(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SystemDrive", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "systemprofile"))
    (tmp_path / "systemprofile").mkdir(exist_ok=True)
    monkeypatch.setenv("USERNAME", "SYSTEM")
    monkeypatch.delenv("BOB_GROK_WEEKLY_USER_HOME", raising=False)
    monkeypatch.delenv("BOB_GROK_AUTH_PATH", raising=False)
    monkeypatch.setattr(bobreport, "_is_local_system_process", lambda: True)

    fake = mock.Mock(
        return_value=mock.Mock(
            returncode=0, stdout="WONDERLAND\\MissingUser6995\n", stderr=""
        )
    )
    monkeypatch.setattr(subprocess, "run", fake)

    assert bobreport._interactive_grok_user_home() is None
    path, identity = bobreport.xai_weekly_auth_path()
    assert path is None
    assert identity == "system-profile-skipped"
