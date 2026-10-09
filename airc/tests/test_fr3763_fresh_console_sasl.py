"""FR #3763: fresh client must not ERROR-log SASL 904 for unregistered {machine}_console.

Skip SASL until ConsoleHome has console.nickserv-ok (written after 903 or NickServ
REGISTER/IDENTIFY success). Fresh install registers via NickServ without a loud 904.
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


def test_fr3763_fresh_home_skips_sasl_and_sends_register(tmp_path, monkeypatch):
    s = make(tmp_path, monkeypatch)
    assert not (tmp_path / "console.nickserv-ok").is_file()
    s.handshake()
    assert not any(l.startswith("AUTHENTICATE") for l in s.sent), s.sent
    assert any(l == "CAP END" for l in s.sent), s.sent
    assert any("PRIVMSG NickServ :REGISTER" in l for l in s.sent), s.sent
    assert any("skip SASL" in m and "FR #3763" in m for m in s.logs), s.logs


def test_fr3763_fresh_904_is_info_not_error(tmp_path, monkeypatch):
    s = make(tmp_path, monkeypatch)
    # Force a 904 even without SASL attempt (defensive path).
    s.on_line(":srv 904 * :SASL authentication failed")
    assert not any(m.startswith("ERROR console account") for m in s.logs), s.logs
    assert any(m.startswith("INFO") and "FR #3763" in m and "904" in m for m in s.logs), s.logs
    assert any(l == "CAP END" for l in s.sent)


def test_fr3763_known_account_904_stays_loud_error(tmp_path, monkeypatch):
    (tmp_path / "console.nickserv-ok").write_text("sasl-903\n", encoding="ascii")
    s = make(tmp_path, monkeypatch)
    s.on_line(":srv 904 * :SASL authentication failed")
    assert any(m.startswith("ERROR console account walrus_console SASL failed") for m in s.logs)
    assert s._sasl_failed


def test_fr3763_known_account_requests_sasl(tmp_path, monkeypatch):
    (tmp_path / "console.nickserv-ok").write_text("prior\n", encoding="ascii")
    s = make(tmp_path, monkeypatch)
    s.handshake()
    assert any(l.startswith("CAP REQ :") and "sasl" in l for l in s.sent), s.sent


def test_fr3763_903_writes_nickserv_ok_marker(tmp_path, monkeypatch):
    s = make(tmp_path, monkeypatch)
    s.on_line(":srv 903 * :SASL authentication successful")
    marker = tmp_path / "console.nickserv-ok"
    assert marker.is_file()
    assert "sasl-903" in marker.read_text(encoding="ascii")


def test_fr3763_nickserv_register_notice_writes_marker(tmp_path, monkeypatch):
    s = make(tmp_path, monkeypatch)
    s.on_line(
        ":NickServ!ns@services NOTICE walrus_console :Account walrus_console is now registered"
    )
    marker = tmp_path / "console.nickserv-ok"
    assert marker.is_file()
    assert "nickserv-notice" in marker.read_text(encoding="ascii")


def test_fr3763_skill_and_source_pins():
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3763" in skill
    assert "console.nickserv-ok" in skill or "nickserv-ok" in skill
    text = SERVICE.read_text(encoding="utf-8")
    assert "FR #3763" in text
    assert "console.nickserv-ok" in text
    assert "skip SASL" in text
