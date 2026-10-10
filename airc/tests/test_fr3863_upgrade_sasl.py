"""FR #3863: upgrade with existing console.password but no nickserv-ok must try SASL.

FR #3763 skipped SASL until console.nickserv-ok existed. Pre-0.1.29 homes never
wrote that marker, so upgrades skipped SASL, hit 433 on the reserved nick, and
looped forever. Reused console.password means try SASL; only a password minted
in this process skips SASL (fresh REGISTER path).
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
    # Upgrade home: GUID already on disk, never wrote nickserv-ok (0.1.28).
    (tmp_path / "console.password").write_text(
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n", encoding="utf-8"
    )
    assert not (tmp_path / "console.nickserv-ok").is_file()
    s = make(tmp_path, monkeypatch)
    assert s._nickserv_account_known()
    assert not getattr(s, "_nickserv_pw_minted", True)
    s.handshake()
    assert any(l.startswith("CAP REQ :") and "sasl" in l for l in s.sent), s.sent
    assert not any("skip SASL" in m for m in s.logs), s.logs
    assert any("FR #3863" in m and "SASL" in m for m in s.logs), s.logs


def test_fr3863_minted_password_still_skips_sasl(tmp_path, monkeypatch):
    # Fresh home: ensure_nickserv_password mints; FR #3763 path unchanged.
    assert not (tmp_path / "console.password").is_file()
    s = make(tmp_path, monkeypatch)
    assert getattr(s, "_nickserv_pw_minted", False)
    assert not s._nickserv_account_known()
    s.handshake()
    assert not any(l.startswith("AUTHENTICATE") for l in s.sent), s.sent
    assert any(l == "CAP END" for l in s.sent), s.sent
    assert any("skip SASL" in m and "FR #3763" in m for m in s.logs), s.logs


def test_fr3863_upgrade_903_writes_marker(tmp_path, monkeypatch):
    (tmp_path / "console.password").write_text(
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n", encoding="utf-8"
    )
    s = make(tmp_path, monkeypatch)
    s.on_line(":srv 903 * :SASL authentication successful")
    marker = tmp_path / "console.nickserv-ok"
    assert marker.is_file()
    assert "sasl-903" in marker.read_text(encoding="ascii")


def test_fr3863_skill_and_source_pins():
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3863" in skill
    assert "nickserv-ok" in skill
    text = SERVICE.read_text(encoding="utf-8")
    assert "FR #3863" in text
    assert "_nickserv_pw_minted" in text
