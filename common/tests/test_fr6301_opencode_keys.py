"""FR #6301 Part D: labelled OpenCode Go keys + no key text in diag/digest."""
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

FAKE_A = "FAKE_OPENCODE_KEY_ALPHA_NOT_REAL"
FAKE_B = "FAKE_OPENCODE_KEY_BRAVO_NOT_REAL"
FAKE_LEGACY = "FAKE_LEGACY_OPENCODE_GO_KEY_NOT_REAL"


def _clear_cache():
    bobreport._opencode_fuel_cache.clear()
    bobreport._opencode_fuel_cache.update({"at": 0.0, "doc": {}})


def test_fr6301_labelled_keys_and_selection(tmp_path, monkeypatch):
    install = tmp_path / "bob"
    keys = install / "config" / "opencode-keys"
    keys.mkdir(parents=True)
    (keys / "alpha.apikey").write_text(FAKE_A + "\n", encoding="utf-8")
    (keys / "bravo.apikey").write_text(FAKE_B + "\n", encoding="utf-8")
    (keys / "selected.txt").write_text("bravo\n", encoding="utf-8")
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(install))
    monkeypatch.delenv("BOB_OPENCODE_GO_API_KEY", raising=False)
    monkeypatch.setattr(bobreport, "tighten_opencode_key_acl", lambda p: False)

    sel = bobreport.resolve_opencode_go_api_key_selection(tighten_acl=False)
    assert sel["label"] == "bravo"
    assert sel["api_key"] == FAKE_B
    assert sel["key_source"] == "labelled-file"
    assert set(sel["labels"]) >= {"alpha", "bravo"}

    (keys / "selected.txt").write_text("alpha\n", encoding="utf-8")
    sel2 = bobreport.resolve_opencode_go_api_key_selection(tighten_acl=False)
    assert sel2["label"] == "alpha"
    assert sel2["api_key"] == FAKE_A


def test_fr6301_legacy_file_only_is_default_label(tmp_path, monkeypatch):
    install = tmp_path / "bob"
    cfg = install / "config"
    cfg.mkdir(parents=True)
    (cfg / "opencode-go.apikey").write_text(FAKE_LEGACY + "\r\n", encoding="utf-8")
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(install))
    monkeypatch.delenv("BOB_OPENCODE_GO_API_KEY", raising=False)
    monkeypatch.setattr(bobreport, "tighten_opencode_key_acl", lambda p: False)

    sel = bobreport.resolve_opencode_go_api_key_selection(tighten_acl=False)
    assert sel["configured"] is True
    assert sel["label"] == "default"
    assert sel["api_key"] == FAKE_LEGACY
    assert sel["key_source"] == "config-file"
    key, src = bobreport.resolve_opencode_go_api_key()
    assert key == FAKE_LEGACY
    assert src == "config-file"


def test_fr6301_same_key_env_and_file_reported_once(tmp_path, monkeypatch):
    install = tmp_path / "bob"
    cfg = install / "config"
    cfg.mkdir(parents=True)
    (cfg / "opencode-go.apikey").write_text(FAKE_LEGACY, encoding="utf-8")
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(install))
    monkeypatch.setenv("BOB_OPENCODE_GO_API_KEY", FAKE_LEGACY)
    monkeypatch.setattr(bobreport, "tighten_opencode_key_acl", lambda p: False)

    sel = bobreport.resolve_opencode_go_api_key_selection(tighten_acl=False)
    assert sel["labels"].count("default") == 1
    assert sel["api_key"] == FAKE_LEGACY
    assert sel["key_source"] == "env"


def test_fr6301_missing_key_is_no_key_set(tmp_path, monkeypatch):
    install = tmp_path / "bob"
    (install / "config").mkdir(parents=True)
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(install))
    for key in (
        "BOB_OPENCODE_GO_API_KEY",
        "BOB_OPENCODE_GO_USAGE_FIXTURE",
        "BOB_OPENCODE_FUEL_FIXTURE",
        "BOB_OPENCODE_WINDOWS_FIXTURE",
        "BOB_OPENCODE_AUTH_PATH",
        "BOB_OPENCODE_SEAT_HOME",
        "BOB_GROK_WEEKLY_USER_HOME",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(bobreport, "_is_local_system_process", lambda: False)
    monkeypatch.setattr(bobreport, "_interactive_grok_user_home", lambda: None)
    monkeypatch.setattr(
        bobreport, "load_opencode_go_key_from_auth", lambda path: ("", "test-isolated")
    )
    monkeypatch.setattr(bobreport, "tighten_opencode_key_acl", lambda p: False)
    # FR #6996: missing bob key with a present binary is "no key set", not "not installed".
    monkeypatch.setattr(
        bobreport,
        "resolve_opencode_exe",
        lambda env=None: (r"C:\fake\opencode.exe", "explicit"),
    )
    _clear_cache()

    doc = bobreport.read_local_opencode_fuel_doc(now=9000.0, force=True)
    acq = bobreport.last_opencode_acquisition()
    assert acq.get("kind") == "missing_key"
    assert acq.get("configured") is False
    assert doc.get("opencode_state") == bobreport.OPENCODE_NO_KEY_STATE
    assert doc.get("source") == "no-key"
    week = (doc.get("windows") or {}).get("week") or {}
    assert week.get("error") == "no key set"
    assert week.get("used_pct") is None
    blob = json.dumps({"doc": doc, "acq": acq})
    assert "FAKE_" not in blob
    assert "apikey" not in blob.lower() or "labelled" in str(acq.get("key_source") or "")


def test_fr6301_no_key_text_in_acquisition_or_publish(tmp_path, monkeypatch):
    install = tmp_path / "bob"
    keys = install / "config" / "opencode-keys"
    keys.mkdir(parents=True)
    (keys / "work.apikey").write_text(FAKE_A, encoding="utf-8")
    (keys / "selected.txt").write_text("work\n", encoding="utf-8")
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(install))
    monkeypatch.delenv("BOB_OPENCODE_GO_API_KEY", raising=False)
    monkeypatch.delenv("BOB_OPENCODE_GO_USAGE_FIXTURE", raising=False)
    monkeypatch.setattr(bobreport, "tighten_opencode_key_acl", lambda p: False)
    _clear_cache()

    def fake_fetch(api_key, *, url=None):
        assert api_key == FAKE_A
        return opencode_fuel.interpret_go_zen_usage_response(
            200, json.dumps(PINNED), now_ms=1_700_000_000_000
        )

    monkeypatch.setattr(opencode_fuel, "fetch_go_zen_usage", fake_fetch)
    doc = bobreport.read_local_opencode_fuel_doc(now=9100.0, force=True)
    assert doc.get("opencode_account") == "work"
    assert doc["windows"]["week"]["reset_label"]
    assert doc["windows"]["week"].get("resets_at")
    acq = bobreport.last_opencode_acquisition()
    assert acq.get("label") == "work"
    blob = json.dumps(acq)
    assert FAKE_A not in blob
    assert "FAKE_OPENCODE" not in blob


def test_fr6301_go_zen_reset_label_and_resets_at_from_reset_in_sec():
    now = 1_700_000_000_000
    read = opencode_fuel.interpret_go_zen_usage_response(
        200, json.dumps(PINNED), now_ms=now
    )
    assert read["kind"] == "json"
    week = read["windows"]["week"]
    assert week["reset_label"] == "6h 32m"
    assert week["resets_at"] == "2023-11-15T04:45:20Z"
    month = read["windows"]["month"]
    assert month["reset_label"] == "25d 22h"
    assert month.get("resets_at")
    # Missing reset is explicit, never invented.
    bare = {"rollingUsage": {"status": "ok", "usagePercent": 10}}
    read2 = opencode_fuel.interpret_go_zen_usage_response(
        200, json.dumps(bare), now_ms=now
    )
    rolling = read2["windows"]["rolling"]
    assert rolling["reset_label"] is None
    assert rolling.get("resets_at") in (None, "")
    assert rolling.get("error") == "reset unavailable"


def test_fr6301_write_helper_script_exists_and_never_echoes_key():
    root = Path(__file__).resolve().parents[2]
    script = root / "bob" / "scripts" / "Write-BobOpencodeGoApiKey.ps1"
    assert script.is_file()
    text = script.read_text(encoding="utf-8")
    assert "Read-Host -AsSecureString" in text
    assert "icacls" in text
    assert "SYSTEM" in text
    assert "Administrators" in text
    # Must not Write-Host the plaintext key variable.
    assert "Write-Host $plain" not in text
    assert "Write-Output $plain" not in text
