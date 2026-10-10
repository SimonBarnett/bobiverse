"""FR #3863: upgrade path — existing console.password + no nickserv-ok must try SASL.

FR #3763 skips SASL for fresh homes (minted GUID, no marker) so unregistered
accounts do not loud-ERROR on 904. Upgraded fleet consoles already own the
NickServ account and keep console.password from 0.1.28, but never wrote
console.nickserv-ok. Skipping SASL then yields 433 reserved-nick loops.
"""
from __future__ import annotations

from pathlib import Path

import airc_console_service as svc
from repo_layout import ROOT

SKILL = (
    ROOT
    / "airc"
    / ".grok"
    / "skills"
    / "bobiverse-airc-troubleshooting"
    / "SKILL.md"
)
SERVICE = ROOT / "airc" / "scripts" / "airc_console_service.py"


def make(tmp_path, monkeypatch, extra=()):
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "x-server-pass")
    args = svc.build_arg_parser().parse_args(
        [
            "--machine",
            "walrus",
            "--home",
            str(tmp_path),
            "--shop-mode",
            "registered",
            "--operators",
            "op",
            *extra,
        ]
    )
    s = svc.AircConsoleService(args)
    s.sent = []
    s.send = lambda line: s.sent.append(line)  # type: ignore[assignment]
    s.logs = []
    monkeypatch.setattr(svc, "info", lambda m: s.logs.append(m))
    return s


def test_fr3863_reused_password_no_marker_requests_sasl(tmp_path, monkeypatch):
    # Upgrade: GUID already on disk from 0.1.28; marker never written.
    (tmp_path / "console.password").write_text(
        "11111111-2222-3333-4444-555555555555\n", encoding="utf-8"
    )
    assert not (tmp_path / "console.nickserv-ok").is_file()
    s = make(tmp_path, monkeypatch)
    assert s._nickserv_password_reused is True
    s.handshake()
    assert any(l.startswith("CAP REQ :") and "sasl" in l for l in s.sent), s.sent
    assert not any("skip SASL" in m for m in s.logs), s.logs


def test_fr3863_fresh_mint_still_skips_sasl(tmp_path, monkeypatch):
    # Fresh install: ensure_nickserv_password mints GUID this run.
    s = make(tmp_path, monkeypatch)
    assert s._nickserv_password_reused is False
    assert not (tmp_path / "console.nickserv-ok").is_file()
    s.handshake()
    assert not any(l.startswith("AUTHENTICATE") for l in s.sent), s.sent
    assert any("skip SASL" in m and "FR #3763" in m for m in s.logs), s.logs


def test_fr3863_reused_password_903_writes_marker(tmp_path, monkeypatch):
    (tmp_path / "console.password").write_text(
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n", encoding="utf-8"
    )
    s = make(tmp_path, monkeypatch)
    s.on_line(":srv 903 * :SASL authentication successful")
    marker = tmp_path / "console.nickserv-ok"
    assert marker.is_file()
    assert "sasl-903" in marker.read_text(encoding="ascii")


def test_fr3863_reused_password_904_is_loud_error(tmp_path, monkeypatch):
    # Wrong GUID vs NickServ after upgrade — loud ERROR (not FR #3763 INFO).
    (tmp_path / "console.password").write_text(
        "deadbeef-dead-beef-dead-beefdeadbeef\n", encoding="utf-8"
    )
    s = make(tmp_path, monkeypatch)
    s.on_line(":srv 904 * :SASL authentication failed")
    assert any(m.startswith("ERROR console account") for m in s.logs), s.logs
    assert s._sasl_failed
    assert not any(
        m.startswith("INFO") and "FR #3763" in m and "904" in m for m in s.logs
    ), s.logs


def test_fr3863_skill_and_source_pins():
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3863" in skill
    assert "console.password" in skill
    text = SERVICE.read_text(encoding="utf-8")
    assert "FR #3863" in text
    assert "_nickserv_password_reused" in text
    assert "_should_attempt_sasl" in text
