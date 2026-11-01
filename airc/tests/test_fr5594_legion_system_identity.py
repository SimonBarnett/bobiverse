"""FR #5594: LEGION default identity is SYSTEM / computer account, not CredMan."""
from __future__ import annotations

from pathlib import Path

import airc_console as ac
import airc_legion as lg
from airc_auth_helpers import ops_auth


def test_fr5594_default_path_no_credman_no_password_env(monkeypatch):
    """FR #5659 amends #5594: CredMan is tried then SYSTEM; missing CredMan falls through."""
    import airc_identity as ident

    seen: list[dict] = []

    def run_fn(spec: dict) -> dict:
        seen.append(spec)
        return {"ok": True, "status": "dry-run"}

    monkeypatch.delenv("AIRC_LEGION_PASSWORD", raising=False)
    monkeypatch.delenv("AIRC_LEGION_USE_CREDMAN", raising=False)
    monkeypatch.setattr(ident, "default_credman_reader", lambda t: {})

    body = lg.installer_legion_work("flamingo", whatif=True, run_fn=run_fn)
    assert body["ok"] is True
    assert body["invoked_installer"] is True
    assert body["identity"] == "system"
    assert body["computer_account"].endswith("$")
    assert body.get("credman_missing") is True
    assert "password" not in body
    assert seen[0].get("identity") == "system"
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


def test_fr5594_explicit_empty_credman_falls_to_system():
    """FR #5659: missing CredMan falls through to SYSTEM (no fail-closed)."""
    seen: list[dict] = []

    def run_fn(spec):
        seen.append(spec)
        return {"ok": True, "status": "ok"}

    body = lg.installer_legion_work(
        "walrus", whatif=False, run_fn=run_fn, credman=lambda: {}
    )
    assert body["ok"] is True
    assert body["invoked_installer"] is True
    assert body["identity"] == "system"
    assert body.get("credman_missing") is True
    assert seen and seen[0].get("identity") == "system"


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
