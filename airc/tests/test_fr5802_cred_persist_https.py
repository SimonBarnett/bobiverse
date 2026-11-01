"""FR #5802: CRED persist via=https writes LocalSystem CredMan (443 path)."""
from __future__ import annotations

import io
import json
from urllib.error import URLError

import airc_console as ac
import airc_passed_cred as pcred
from airc_auth_helpers import ops_auth

FAKE_PW = "FAKE_" + "5802_cred_pw"
FAKE_USER = "Tabula"
QID = "c5802001"
TARGET = "PriorityWeb/hrs-priority-dev"
URL = "https://bob.ntsa.uk/bob/v1/cred-once/example"


def _core():
    auth = ops_auth("op", channel="#tm")
    return ac.AircConsoleCore(
        machine="tm",
        auth=auth,
        nick="tm_console",
        shell_runner=None,
    )


def test_fr5802_parse_persist_https():
    parsed = pcred.parse_cred_command(
        f"id={QID} CRED persist target={TARGET} via=https url={URL}"
    )
    assert parsed is not None
    assert parsed["qid"] == QID
    assert parsed["persist"] is True
    assert parsed["via"] == "https"
    assert parsed["target"] == TARGET
    assert parsed["url"] == URL


def test_fr5802_https_url_allowlist():
    assert pcred.https_cred_url_allowed(URL) is True
    assert pcred.https_cred_url_allowed("http://bob.ntsa.uk/x") is False
    assert pcred.https_cred_url_allowed("https://evil.example/x") is False
    assert (
        pcred.https_cred_url_allowed(
            "https://drops.example/cred.json",
            env={"AIRC_CRED_HTTPS_PREFIXES": "https://drops.example/"},
        )
        is True
    )


def test_fr5802_fetch_classifies_firewall(monkeypatch):
    def boom(_req, timeout=None):
        raise URLError(OSError("10060"))

    monkeypatch.setattr(
        pcred,
        "https_cred_url_allowed",
        lambda *_a, **_k: True,
    )
    try:
        pcred.fetch_cred_json_https(URL, opener=boom)
        raise AssertionError("expected fail")
    except ValueError as exc:
        assert "firewall-or-unreachable" in str(exc)


def test_fr5802_persist_https_writes_credman(monkeypatch):
    written: list[tuple[str, str, str]] = []
    payload = json.dumps({"username": FAKE_USER, "password": FAKE_PW}).encode("utf-8")

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_open(_req, timeout=None):
        return _Resp(payload)

    def fake_write(target, username, password):
        written.append((target, username, password))

    monkeypatch.setattr(pcred, "fetch_cred_json_https", lambda url, **k: pcred.parse_cred_json(payload))
    # Route persist_credman writer
    real_persist = pcred.persist_credman

    def wrap(target, username, password, writer=None):
        return real_persist(target, username, password, writer=fake_write)

    monkeypatch.setattr(pcred, "persist_credman", wrap)

    core = _core()
    hr = core.handle_raw(
        f":op!u@h PRIVMSG tm_console :id={QID} CRED persist "
        f"target={TARGET} via=https url={URL}"
    )
    assert hr is not None
    assert hr.action == "cred"
    text = hr.reply or ""
    assert f"CRED persisted target={TARGET}" in text
    assert f"cred-persisted target={TARGET}" in text
    assert f"account={FAKE_USER}" in text
    assert FAKE_PW not in text
    assert "password=" not in text.lower()
    assert written == [(TARGET, FAKE_USER, FAKE_PW)]


def test_fr5802_persist_url_rejected(monkeypatch):
    core = _core()
    hr = core.handle_raw(
        f":op!u@h PRIVMSG tm_console :id={QID} CRED persist "
        f"target={TARGET} via=https url=https://evil.example/secret.json"
    )
    assert hr is not None
    text = hr.reply or ""
    assert "cred failed:" in text
    assert "cred-url-rejected" in text
    assert FAKE_PW not in text


def test_fr5802_write_helper_source_pins():
    import airc_credman as cm

    assert hasattr(cm, "write_generic_credential")
    assert cm.CRED_PERSIST_LOCAL_MACHINE == 2


def test_fr5802_skill_and_docs_pins():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    cmd = (root / "airc/.grok/skills/bobiverse-airc-commands/SKILL.md").read_text(
        encoding="utf-8"
    )
    tro = (
        root / "airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md"
    ).read_text(encoding="utf-8")
    docs = (root / "airc/docs/airc-remote-control.md").read_text(encoding="utf-8")
    assert "CRED persist" in cmd
    assert "via=https" in cmd
    assert "FR #5802" in cmd
    assert "FR #5802" in tro
    assert "cred-url-rejected" in tro
    assert "CRED persist (FR #5802)" in docs
