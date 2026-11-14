"""FR #7177: LocalSystem ear fetches OpenCode Go usage (no missing_key / empty-as-fresh).

Si: if the service runs as SYSTEM and cannot fetch as SYSTEM, that is a bug.
Key comes from service-configured install config / env (never logged). Empty
usage with an advancing timestamp is a failure.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import bobreport
import opencode_fuel as of


FAKE_KEY = "FAKE_OPENCODE_GO_KEY_7177"


def _system_env(monkeypatch, tmp_path: Path, *, install: Path) -> None:
    sys_home = tmp_path / "systemprofile"
    sys_home.mkdir(exist_ok=True)
    monkeypatch.setenv("USERPROFILE", str(sys_home))
    monkeypatch.setenv("LOCALAPPDATA", str(sys_home / "AppData" / "Local"))
    (sys_home / "AppData" / "Local").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("USERNAME", "SYSTEM")
    monkeypatch.setenv("SystemDrive", str(tmp_path))
    monkeypatch.delenv("BOB_INSTALL_ROOT", raising=False)
    monkeypatch.delenv("BOB_OPENCODE_GO_API_KEY", raising=False)
    monkeypatch.delenv("BOB_OPENCODE_AUTH_PATH", raising=False)
    monkeypatch.delenv("BOB_OPENCODE_GO_USAGE_FIXTURE", raising=False)
    monkeypatch.delenv("BOB_OPENCODE_FUEL_FIXTURE", raising=False)
    monkeypatch.delenv("BOB_OPENCODE_EXE", raising=False)
    monkeypatch.delenv("BOB_GROK_WEEKLY_USER_HOME", raising=False)
    monkeypatch.setattr(bobreport, "_is_local_system_process", lambda: True)
    monkeypatch.setattr(bobreport, "_interactive_grok_user_home", lambda: None)
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


def _usage_body(used: float = 25.0) -> str:
    return json.dumps(
        {
            "rollingUsage": {"usagePercent": used, "resetInSec": 3600},
            "weeklyUsage": {"usagePercent": used + 1, "resetInSec": 86400},
            "monthlyUsage": {"usagePercent": used + 2, "resetInSec": 604800},
        }
    )


def test_fr7177_frozen_root_finds_labelled_key_without_bob_install_root(
    monkeypatch, tmp_path: Path
):
    install = tmp_path / "bob"
    _system_env(monkeypatch, tmp_path, install=install)
    keys = install / "config" / "opencode-keys"
    keys.mkdir(parents=True)
    (keys / "default.apikey").write_text(FAKE_KEY, encoding="utf-8")

    sel = bobreport.resolve_opencode_go_api_key_selection(tighten_acl=False)
    assert sel["api_key"] == FAKE_KEY
    assert sel["root_origin"] == "exe"
    assert sel["configured"] is True
    assert FAKE_KEY not in json.dumps({k: v for k, v in sel.items() if k != "api_key"})


def test_fr7177_empty_usage_is_failure_not_fresh(monkeypatch, tmp_path: Path):
    install = tmp_path / "bob"
    _system_env(monkeypatch, tmp_path, install=install)
    keys = install / "config" / "opencode-keys"
    keys.mkdir(parents=True)
    (keys / "default.apikey").write_text(FAKE_KEY, encoding="utf-8")
    # Recognised layout, no usable meters.
    monkeypatch.setenv(
        "BOB_OPENCODE_GO_USAGE_FIXTURE",
        "200\n" + json.dumps({"usage": {}}),
    )
    bobreport._opencode_fuel_cache.clear()
    doc = bobreport.read_local_opencode_fuel_doc(force=True)
    acq = bobreport.last_opencode_acquisition()
    assert acq.get("kind") == "empty"
    wins = doc.get("windows") or {}
    for wid in ("rolling", "week", "month"):
        rec = wins.get(wid) or {}
        assert rec.get("fetched_at") is None
        assert rec.get("remaining_pct") is None
    assert not (doc.get("pcent") or {}).get("opencode-go")


def test_fr7177_missing_key_windows_have_null_fetched_at(monkeypatch, tmp_path: Path):
    install = tmp_path / "bob"
    _system_env(monkeypatch, tmp_path, install=install)
    # Pretend opencode.exe exists so path is missing_key not not_installed.
    monkeypatch.setattr(
        bobreport,
        "resolve_opencode_exe",
        lambda env=None: (str(install / "opencode.exe"), "explicit"),
    )
    bobreport._opencode_fuel_cache.clear()
    doc1 = bobreport.read_local_opencode_fuel_doc(force=True)
    doc2 = bobreport.read_local_opencode_fuel_doc(force=True)
    assert bobreport.last_opencode_acquisition().get("kind") == "missing_key"
    for doc in (doc1, doc2):
        wins = doc.get("windows") or {}
        for wid in ("rolling", "week", "month"):
            assert (wins.get(wid) or {}).get("fetched_at") is None
            assert (wins.get(wid) or {}).get("error") == "no key set"
    # Fingerprint must not churn on empty missing_key polls.
    assert bobreport.peer_fuel_fingerprint(
        {"opencode_windows": doc1.get("windows"), "pcent": {}}
    ) == bobreport.peer_fuel_fingerprint(
        {"opencode_windows": doc2.get("windows"), "pcent": {}}
    )


def test_fr7177_localsystem_live_fetch_advances_fetched_at(
    monkeypatch, tmp_path: Path
):
    install = tmp_path / "bob"
    _system_env(monkeypatch, tmp_path, install=install)
    keys = install / "config" / "opencode-keys"
    keys.mkdir(parents=True)
    (keys / "default.apikey").write_text(FAKE_KEY, encoding="utf-8")

    calls = {"n": 0}
    used = [20.0, 21.0]

    def fake_fetch(api_key, **kwargs):
        assert api_key == FAKE_KEY
        i = calls["n"]
        calls["n"] = i + 1
        return of.interpret_go_zen_usage_response(
            200,
            _usage_body(used[i]),
            now_ms=1_700_000_000_000 + i * 300_000,
        )

    bobreport._opencode_fuel_cache.clear()
    with mock.patch.object(of, "fetch_go_zen_usage", side_effect=fake_fetch):
        d1 = bobreport.read_local_opencode_fuel_doc(force=True)
        d2 = bobreport.read_local_opencode_fuel_doc(force=True)
    assert calls["n"] == 2
    assert bobreport.last_opencode_acquisition().get("kind") == "json"
    assert bobreport.last_opencode_acquisition().get("key_source") in (
        "labelled-file",
        "config-file",
        "env",
    )
    w1 = (d1.get("windows") or {}).get("rolling") or {}
    w2 = (d2.get("windows") or {}).get("rolling") or {}
    assert w1.get("status") == "known"
    assert w2.get("status") == "known"
    assert w1.get("fetched_at")
    assert w2.get("fetched_at")
    assert w1["fetched_at"] != w2["fetched_at"]
    assert (d1.get("pcent") or {}).get("opencode-go") is not None
    assert (d2.get("pcent") or {}).get("opencode-go") is not None


def test_fr7177_unreadable_labelled_key_is_key_unreadable_not_missing_key(
    monkeypatch, tmp_path: Path
):
    """SYSTEM must not collapse an unreadable *.apikey into missing_key (MRB #7190)."""
    install = tmp_path / "bob"
    _system_env(monkeypatch, tmp_path, install=install)
    keys = install / "config" / "opencode-keys"
    keys.mkdir(parents=True)
    path = keys / "default.apikey"
    path.write_text(FAKE_KEY, encoding="utf-8")

    monkeypatch.setattr(bobreport, "tighten_opencode_key_acl", lambda p: False)
    monkeypatch.setattr(
        bobreport,
        "_read_opencode_key_file_ex",
        lambda p: ("", "key-file-unreadable"),
    )
    monkeypatch.setattr(
        bobreport,
        "resolve_opencode_exe",
        lambda env=None: (str(install / "opencode.exe"), "explicit"),
    )
    bobreport._opencode_fuel_cache.clear()
    sel = bobreport.resolve_opencode_go_api_key_selection(tighten_acl=False)
    assert not sel.get("api_key")
    assert sel.get("key_error") == "key-file-unreadable"
    doc = bobreport.read_local_opencode_fuel_doc(force=True)
    assert bobreport.last_opencode_acquisition().get("kind") == "key_unreadable"
    assert bobreport.last_opencode_acquisition().get("kind") != "missing_key"
    wins = doc.get("windows") or {}
    for wid in ("rolling", "week", "month"):
        assert (wins.get(wid) or {}).get("fetched_at") is None


def test_fr7177_install_bob_preserves_nssm_go_key_without_echo():
    from repo_layout import ROOT

    text = (ROOT / "bob" / "scripts" / "Install-Bob.ps1").read_text(encoding="utf-8")
    assert "priorOpencodeGoApiKeyLine" in text
    assert "BOB_OPENCODE_GO_API_KEY=" in text
    assert "Write-Host $priorOpencodeGoApiKeyLine" not in text


def test_fr7177_interpret_empty_vs_malformed():
    empty = of.interpret_go_zen_usage_response(200, json.dumps({"usage": {}}))
    assert empty["kind"] == "empty"
    for wid in ("rolling", "week", "month"):
        assert (empty["windows"][wid].get("fetched_at") is None)
    bad = of.interpret_go_zen_usage_response(200, "{}")
    assert bad["kind"] == "malformed"
    partial = of.interpret_go_zen_usage_response(
        200,
        json.dumps(
            {
                "usage": {
                    "rolling": {"percent": 10},
                    "weekly": None,
                    "monthly": None,
                }
            }
        ),
    )
    assert partial["kind"] == "json"
    assert partial["windows"]["rolling"]["fetched_at"]
    assert partial["windows"]["week"]["fetched_at"] is None
