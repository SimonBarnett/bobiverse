"""FR #6441: AD/CredMan auth gate for Jeeves appliance settings."""
from __future__ import annotations

import json
from pathlib import Path

import jeeves_settings as js
import jeeves_settings_auth as auth


def test_fr6441_unauthenticated_api_rejected(tmp_path, monkeypatch):
    home = tmp_path / "h"
    home.mkdir()
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    view = auth.api_get_settings_authed(home, client_ip="10.0.0.8", session_token="")
    assert view["ok"] is False
    assert view["error"].startswith("unauthorized")
    put = auth.api_put_setting_authed(
        home, client_ip="10.0.0.8", session_token=None,
        key="BOB_CODERABBIT_WAIT_MIN", value="9",
    )
    assert put["ok"] is False
    assert put["error"].startswith("unauthorized")


def test_fr6441_login_rejects_non_lan(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    r = auth.login(
        home, client_ip="8.8.8.8", username="admin", password="x",
        authenticator=lambda u, p, d="": True,
    )
    assert r["ok"] is False
    assert "forbidden" in r["error"]


def test_fr6441_bad_credentials_rejected(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    r = auth.login(
        home, client_ip="10.0.0.8", username="admin", password="wrong",
        authenticator=lambda u, p, d="": False,
    )
    assert r["ok"] is False
    assert "unauthorized" in r["error"]
    # Never echo password in response
    assert "wrong" not in json.dumps(r)


def test_fr6441_login_session_then_authed_get_put(tmp_path, monkeypatch):
    home = tmp_path / "h"
    home.mkdir()
    monkeypatch.setenv("GH_TOKEN", "ghs_FAKESECRET_SHOULD_NOT_LEAK")
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    r = auth.login(
        home, client_ip="10.0.0.8", username="ApplianceAdmin", password="FAKE_ok",
        authenticator=lambda u, p, d="": u == "ApplianceAdmin" and p == "FAKE_ok",
    )
    assert r["ok"] is True
    tok = r["session_token"]
    assert tok and "FAKE_ok" not in tok
    view = auth.api_get_settings_authed(home, client_ip="10.0.0.8", session_token=tok)
    assert view["ok"] is True
    blob = json.dumps(view)
    assert "ghs_FAKESECRET" not in blob
    assert "SHOULD_NOT_LEAK" not in blob
    secrets = [row for row in view["settings"] if row["key"] == "GH_TOKEN"]
    assert secrets and secrets[0]["value"] in ("set", "unset")
    put = auth.api_put_setting_authed(
        home, client_ip="10.0.0.8", session_token=tok,
        key="BOB_CODERABBIT_WAIT_MIN", value="15", actor="ignored",
    )
    assert put["ok"] is True
    # Actor stamped from session, not caller spoof
    audit = (home / "settings-audit.jsonl").read_text(encoding="utf-8")
    assert "ApplianceAdmin" in audit
    assert "FAKE_ok" not in audit


def test_fr6441_session_file_never_stores_password(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    auth.login(
        home, client_ip="10.0.0.8", username="u1", password="FAKE_secret_pw",
        authenticator=lambda u, p, d="": True,
    )
    raw = (home / auth.SESSION_STORE).read_text(encoding="utf-8")
    assert "FAKE_secret_pw" not in raw
    doc = json.loads(raw)
    blob = json.dumps(doc)
    assert "FAKE_secret_pw" not in blob
    for row in (doc.get("sessions") or {}).values():
        assert "password" not in row
        assert "token" not in row


def test_fr6441_expired_or_unknown_session_rejected(tmp_path, monkeypatch):
    home = tmp_path / "h"
    home.mkdir()
    monkeypatch.setattr(auth, "SESSION_TTL_S", 1)
    r = auth.login(
        home, client_ip="10.0.0.8", username="u1", password="x",
        authenticator=lambda u, p, d="": True, now=1000.0,
    )
    tok = r["session_token"]
    bad = auth.require_session(home, client_ip="10.0.0.8", session_token=tok, now=1000.0 + 2)
    assert bad["ok"] is False
    unknown = auth.require_session(home, client_ip="10.0.0.8", session_token="nope")
    assert unknown["ok"] is False


def test_fr6441_credman_authenticator_uses_injected_reader(tmp_path):
    def reader(target: str):
        assert target == auth.CREDMAN_TARGET
        return {"username": "ApplianceAdmin", "password": "FAKE_from_credman"}

    ok = auth.authenticate_credman(
        "ApplianceAdmin", "FAKE_from_credman", cred_reader=reader
    )
    assert ok is True
    bad = auth.authenticate_credman(
        "ApplianceAdmin", "FAKE_wrong", cred_reader=reader
    )
    assert bad is False
    missing = auth.authenticate_credman(
        "ApplianceAdmin", "x", cred_reader=lambda t: {}
    )
    assert missing is False


def test_fr6441_docs_describe_credman_and_ad():
    root = Path(__file__).resolve().parents[2]
    doc = root / "jeeves" / "docs" / "jeeves-settings-appliance.md"
    text = doc.read_text(encoding="utf-8")
    assert "CredMan" in text or "credman" in text.lower()
    assert auth.CREDMAN_TARGET in text or "Jeeves/ApplianceAdmin" in text
    assert "LogonUser" in text or "AD" in text or "Active Directory" in text
    assert "session" in text.lower()
    assert b"\xef\xbb\xbf" not in doc.read_bytes()[:4]


def test_fr6441_vision_lists_auth_child():
    vision = Path(__file__).resolve().parents[2] / "jeeves" / "VISION.md"
    text = vision.read_text(encoding="utf-8")
    assert "6441" in text or "CredMan" in text or "AD" in text
