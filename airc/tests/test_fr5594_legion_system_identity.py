"""FR #5594: LEGION default identity is SYSTEM / computer account, not CredMan."""
from __future__ import annotations

from pathlib import Path

import airc_console as ac
import airc_legion as lg
from airc_auth_helpers import ops_auth


def test_fr5594_default_path_no_credman_no_password_env(monkeypatch):
    calls = {"credman": 0}
    seen: list[dict] = []

    def boom_credman():
        calls["credman"] += 1
        raise AssertionError("default path must not read CredMan")

    def run_fn(spec: dict) -> dict:
        seen.append(spec)
        return {"ok": True, "status": "dry-run"}

    monkeypatch.delenv("AIRC_LEGION_PASSWORD", raising=False)
    monkeypatch.delenv("AIRC_LEGION_USE_CREDMAN", raising=False)
    monkeypatch.setattr(lg, "default_legion_credman", boom_credman)
    monkeypatch.setattr(lg, "read_legion_credman", boom_credman)

    body = lg.installer_legion_work("flamingo", whatif=True, run_fn=run_fn)
    assert calls["credman"] == 0
    assert body["ok"] is True
    assert body["invoked_installer"] is True
    assert body["identity"] == "SYSTEM"
    assert body["computer_account"].endswith("$")
    assert "password" not in body
    assert seen[0].get("identity") == "SYSTEM"
    assert "username" not in seen[0]
    assert "password" not in seen[0]
    assert not seen[0].get("password_via")
    assert not os_env_has_legion_password()


def os_env_has_legion_password() -> bool:
    import os

    return bool(os.environ.get("AIRC_LEGION_PASSWORD"))


def test_fr5594_identity_label_uses_computer_account():
    ident = lg.legion_system_identity(
        hostname_fn=lambda: "MarchHare",
        domain_fn=lambda: "WONDERLAND",
    )
    assert ident["identity"] == "SYSTEM"
    assert ident["computer_account"] == "WONDERLAND\\MARCHHARE$"
    assert ident["identity_label"] == "SYSTEM (WONDERLAND\\MARCHHARE$)"


def test_fr5594_access_denied_maps_to_system_reason():
    def run_fn(spec: dict) -> dict:
        return {
            "ok": False,
            "status": "failed",
            "error": "Access is denied. ADMIN$ / SCM",
        }

    body = lg.installer_legion_work("flamingo", whatif=False, run_fn=run_fn)
    assert body["ok"] is False
    assert body["error"] == "system-access-denied"
    assert "Administrators" in (body.get("hint") or "")
    assert body["target"] == "flamingo"


def test_fr5594_explicit_empty_credman_still_fail_closed():
    def boom_run(spec):
        raise AssertionError("installer must not run")

    body = lg.installer_legion_work(
        "walrus", whatif=False, run_fn=boom_run, credman=lambda: {}
    )
    assert body["ok"] is False
    assert body["invoked_installer"] is False
    assert body["error"] == "credman-missing"


def test_fr5594_console_default_is_not_credman_missing():
    auth = ops_auth("op", channel="#tm")

    def runner(**kw):
        return lg.run_legion_verb(wait=True, **kw)

    core = ac.AircConsoleCore(
        machine="tm", auth=auth, nick="tm_console", legion_runner=runner
    )
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=aabbccdd LEGION walrus -WhatIf")
    assert hr and hr.action == "legion"
    assert "credman-missing" not in (hr.reply or "")
    assert "126" not in (hr.reply or "").split()


def test_fr5594_pins():
    srcp = Path(lg.__file__).resolve()
    src = srcp.read_text(encoding="utf-8")
    assert "FR #5594" in src
    assert "system-access-denied" in src
    assert "legion_system_identity" in src
    docs = srcp.parents[1] / "docs" / "airc-remote-control.md"
    assert "computer account" in docs.read_text(encoding="utf-8").lower()
    assert not srcp.read_bytes().startswith(b"\xef\xbb\xbf")
