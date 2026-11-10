"""docs/mrb-6450: hostile pins for FR #6441 appliance auth (PR #6450)."""
from __future__ import annotations

import json
from pathlib import Path

import jeeves_settings_auth as auth


def test_docs_mrb6450_rollback_authed_requires_session(tmp_path, monkeypatch):
    home = tmp_path / "h"
    home.mkdir()
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    denied = auth.api_rollback_authed(
        home, client_ip="10.0.0.8", session_token="", backup_id="nope"
    )
    assert denied["ok"] is False
    assert str(denied.get("error") or "").startswith("unauthorized")

    r = auth.login(
        home,
        client_ip="10.0.0.8",
        username="ApplianceAdmin",
        password="FAKE_ok",
        authenticator=lambda u, p, d="": True,
    )
    assert r["ok"] is True
    put = auth.api_put_setting_authed(
        home,
        client_ip="10.0.0.8",
        session_token=r["session_token"],
        key="BOB_CODERABBIT_WAIT_MIN",
        value="12",
    )
    assert put["ok"] is True
    rb = auth.api_rollback_authed(
        home,
        client_ip="10.0.0.8",
        session_token=r["session_token"],
        backup_id=put["backup_id"],
    )
    assert rb["ok"] is True


def test_docs_mrb6450_build_imports_auth_http_stall():
    build = (
        Path(__file__).resolve().parents[2]
        / "jeeves"
        / "scripts"
        / "Build-Jeeves.ps1"
    ).read_text(encoding="utf-8")
    assert "jeeves_settings_auth" in build
    assert "jeeves_settings_http" in build
    assert "stall_callbacks" in build
    assert build.count("'jeeves_settings'") + build.count('"jeeves_settings"') >= 1
    assert "<<<<<<<" not in build


def test_docs_mrb6450_docs_and_vision_keep_auth_and_http():
    root = Path(__file__).resolve().parents[2]
    doc = (root / "jeeves" / "docs" / "jeeves-settings-appliance.md").read_text(
        encoding="utf-8"
    )
    vision = (root / "jeeves" / "VISION.md").read_text(encoding="utf-8")
    assert "FR #6441" in doc or "6441" in doc
    assert "Jeeves/ApplianceAdmin" in doc
    assert "JEEVES_SETTINGS_HTTP" in doc
    assert "jeeves_settings_auth" in vision
    assert "6440" in vision and "6441" in vision


def test_docs_mrb6450_http_uses_authed_helpers():
    """FR #6451 closed the gap: HTTP module calls api_*_authed."""
    http_src = (
        Path(__file__).resolve().parents[2]
        / "common"
        / "scripts"
        / "jeeves_settings_http.py"
    ).read_text(encoding="utf-8")
    assert "api_get_settings_authed" in http_src
    assert "api_put_setting_authed" in http_src
    assert "/api/login" in http_src
