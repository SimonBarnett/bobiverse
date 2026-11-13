"""FR #6996: LocalSystem ear finds per-user WinGet OpenCode and user auth.json.

Never asserts or prints a live key. Fixtures use FAKE_ placeholders only.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import bobreport
import opencode_fuel

PINNED = {
    "useBalance": True,
    "rollingUsage": {"status": "ok", "usagePercent": 0, "resetInSec": 3600},
    "weeklyUsage": {"status": "ok", "usagePercent": 72, "resetInSec": 23520},
    "monthlyUsage": {"status": "ok", "usagePercent": 36, "resetInSec": 2239200},
}

FAKE_GO = "FAKE_OPENCODE_GO_KEY_FROM_USER_AUTH_NOT_REAL"


def _clear_cache():
    bobreport._opencode_fuel_cache.clear()
    bobreport._opencode_fuel_cache.update({"at": 0.0, "doc": {}})


def _system_env(tmp_path: Path, monkeypatch, *, user_name="FleetAdmin"):
    sysprof = tmp_path / "Windows" / "system32" / "config" / "systemprofile"
    sysprof.mkdir(parents=True)
    monkeypatch.setenv("USERPROFILE", str(sysprof))
    monkeypatch.setenv("HOME", str(sysprof))
    monkeypatch.setenv("USERNAME", "SYSTEM")
    monkeypatch.setenv("LOCALAPPDATA", str(sysprof / "AppData" / "Local"))
    monkeypatch.delenv("BOB_OPENCODE_GO_API_KEY", raising=False)
    monkeypatch.delenv("BOB_OPENCODE_GO_USAGE_FIXTURE", raising=False)
    monkeypatch.delenv("BOB_OPENCODE_FUEL_FIXTURE", raising=False)
    monkeypatch.delenv("BOB_OPENCODE_WINDOWS_FIXTURE", raising=False)
    monkeypatch.delenv("BOB_OPENCODE_EXE", raising=False)
    monkeypatch.delenv("BOB_OPENCODE_AUTH_PATH", raising=False)
    monkeypatch.delenv("BOB_OPENCODE_SEAT_HOME", raising=False)
    install = tmp_path / "bob"
    (install / "config").mkdir(parents=True)
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(install))
    user = tmp_path / "Users" / user_name
    user.mkdir(parents=True)
    return sysprof, user, install


def test_fr6996_system_finds_interactive_winget_links(tmp_path, monkeypatch):
    _sysprof, user, _install = _system_env(tmp_path, monkeypatch)
    exe = user / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links" / "opencode.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"MZ")
    monkeypatch.setattr(bobreport, "_interactive_grok_user_home", lambda: user)
    monkeypatch.setattr(bobreport, "_is_local_system_process", lambda: True)

    path, ident = bobreport.resolve_opencode_exe()
    assert path is not None
    assert Path(path) == exe
    assert ident == "interactive-winget"


def test_fr6996_system_missing_exe_is_not_installed(tmp_path, monkeypatch):
    _sysprof, user, _install = _system_env(tmp_path, monkeypatch)
    monkeypatch.setattr(bobreport, "_interactive_grok_user_home", lambda: user)
    monkeypatch.setattr(bobreport, "_is_local_system_process", lambda: True)
    monkeypatch.setattr(bobreport, "tighten_opencode_key_acl", lambda p: False)
    monkeypatch.setattr(bobreport.shutil, "which", lambda *_a, **_k: None)
    _clear_cache()

    path, ident = bobreport.resolve_opencode_exe()
    assert path is None
    assert ident == "missing"

    doc = bobreport.read_local_opencode_fuel_doc(now=12000.0, force=True)
    acq = bobreport.last_opencode_acquisition()
    assert acq.get("kind") == "not_installed"
    assert acq.get("exe_source") == "missing"
    assert doc.get("opencode_state") == bobreport.OPENCODE_NOT_INSTALLED_STATE
    week = (doc.get("windows") or {}).get("week") or {}
    assert week.get("error") == "not installed"
    blob = json.dumps({"doc": doc, "acq": acq})
    assert FAKE_GO not in blob
    assert "FAKE_" not in blob


def test_fr6996_user_auth_json_supplies_go_key_without_logging(tmp_path, monkeypatch):
    _sysprof, user, _install = _system_env(tmp_path, monkeypatch)
    exe = user / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links" / "opencode.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"MZ")
    auth = user / ".local" / "share" / "opencode" / "auth.json"
    auth.parent.mkdir(parents=True)
    auth.write_text(
        json.dumps({"opencode-go": {"type": "api", "key": FAKE_GO}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(bobreport, "_interactive_grok_user_home", lambda: user)
    monkeypatch.setattr(bobreport, "_is_local_system_process", lambda: True)
    monkeypatch.setattr(bobreport, "tighten_opencode_key_acl", lambda p: False)
    _clear_cache()

    sel = bobreport.resolve_opencode_go_api_key_selection(tighten_acl=False)
    assert sel["configured"] is True
    assert sel["api_key"] == FAKE_GO
    assert sel["key_source"] == "user-auth"

    captured = {}

    def fake_fetch(api_key, *, url=None, timeout=5.0, now_ms=None):
        captured["key"] = api_key
        return opencode_fuel.interpret_go_zen_usage_response(
            200, json.dumps(PINNED), now_ms=1_700_000_000_000
        )

    monkeypatch.setattr(opencode_fuel, "fetch_go_zen_usage", fake_fetch)
    doc = bobreport.read_local_opencode_fuel_doc(now=12100.0, force=True)
    assert captured["key"] == FAKE_GO
    assert doc["windows"]["week"]["used_pct"] == 72
    acq = bobreport.last_opencode_acquisition()
    assert acq.get("key_source") == "user-auth"
    assert acq.get("exe_source") == "interactive-winget"
    blob = json.dumps(acq)
    assert FAKE_GO not in blob
    assert "FAKE_OPENCODE" not in blob


def test_fr6996_extract_go_key_ignores_non_go_slots():
    doc = {
        "opencode": {"type": "api", "key": "FAKE_FREE_SLOT_NOT_GO"},
        "opencode-go": {"type": "api", "key": FAKE_GO},
    }
    assert bobreport.extract_opencode_go_key_from_auth_doc(doc) == FAKE_GO
    assert bobreport.extract_opencode_go_key_from_auth_doc({}) == ""
    assert bobreport.extract_opencode_go_key_from_auth_doc(None) == ""


def test_fr6996_bob_config_key_beats_user_auth(tmp_path, monkeypatch):
    _sysprof, user, install = _system_env(tmp_path, monkeypatch)
    cfg_key = "FAKE_BOB_CONFIG_OPENCODE_GO_KEY_NOT_REAL"
    (install / "config" / "opencode-go.apikey").write_text(cfg_key, encoding="utf-8")
    auth = user / ".local" / "share" / "opencode" / "auth.json"
    auth.parent.mkdir(parents=True)
    auth.write_text(
        json.dumps({"opencode-go": {"type": "api", "key": FAKE_GO}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(bobreport, "_interactive_grok_user_home", lambda: user)
    monkeypatch.setattr(bobreport, "tighten_opencode_key_acl", lambda p: False)
    sel = bobreport.resolve_opencode_go_api_key_selection(tighten_acl=False)
    assert sel["api_key"] == cfg_key
    assert sel["key_source"] == "config-file"


def test_fr6996_hover_paints_not_installed():
    src = (
        Path(__file__).resolve().parents[2]
        / "bob"
        / "tray"
        / "src"
        / "Public"
        / "Get-BobTrayHover.ps1"
    ).read_text(encoding="utf-8")
    assert "not installed" in src
    assert "no key set" in src


def test_fr6996_helper_ps1_resolves_interactive_winget():
    src = (
        Path(__file__).resolve().parents[2]
        / "bob"
        / "tray"
        / "tools"
        / "Get-BobOpencodeFuel.ps1"
    ).read_text(encoding="utf-8")
    assert "WinGet\\Links\\opencode.exe" in src
    assert "BOB_OPENCODE_SEAT_HOME" in src or "BOB_GROK_WEEKLY_USER_HOME" in src
    assert "AppData\\Local" in src
    assert "IsSystem" in src


def test_fr6996_worker_resolve_uses_interactive_winget(tmp_path, monkeypatch):
    import bob_worker as bw

    sysprof = tmp_path / "systemprofile"
    sysprof.mkdir()
    user = tmp_path / "Users" / "Administrator"
    exe = user / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links" / "opencode.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"MZ")
    monkeypatch.setenv("USERPROFILE", str(sysprof))
    monkeypatch.setenv("LOCALAPPDATA", str(sysprof / "AppData" / "Local"))
    monkeypatch.setenv("USERNAME", "SYSTEM")
    monkeypatch.setenv("BOB_OPENCODE_SEAT_HOME", str(user))
    found = bw.resolve_opencode_cmd()
    assert found == str(exe)
