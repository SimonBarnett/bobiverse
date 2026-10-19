"""FR #4789: reserved-nick 433 while skip-SASL must recover via SASL, not loop.

When console.password exists but console.nickserv-ok is missing and the process
still treats the GUID as minted (stale console.password-minted), tip used to skip
SASL, hit 433 on the reserved {machine}_console nick, and reconnect forever.
"""
from __future__ import annotations

import os
from pathlib import Path

import airc_console_service as svc
from repo_layout import ROOT

SERVICE = ROOT / "airc" / "scripts" / "airc_console_service.py"
SKILL = (
    ROOT
    / "airc"
    / ".grok"
    / "skills"
    / "bobiverse-airc-troubleshooting"
    / "SKILL.md"
)


def make(tmp_path, monkeypatch, machine="rm-sql01", extra=()):
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "x-server-pass")
    args = svc.build_arg_parser().parse_args(
        [
            "--machine",
            machine,
            "--home",
            str(tmp_path),
            "--shop-mode",
            "wonderland",
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


def test_fr4789_stale_mint_marker_skips_sasl_until_433(tmp_path, monkeypatch):
    """password-minted + existing GUID → skip SASL at handshake (FR #3900)."""
    (tmp_path / "console.password").write_text(
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n", encoding="utf-8"
    )
    (tmp_path / "console.password-minted").write_text("install\n", encoding="ascii")
    assert not (tmp_path / "console.nickserv-ok").is_file()
    s = make(tmp_path, monkeypatch)
    assert s._nickserv_pw_minted is True
    assert not s._nickserv_account_known()
    s.handshake()
    assert any("skip SASL" in m and "FR #3763" in m for m in s.logs), s.logs
    assert not any(l.startswith("CAP REQ :") and "sasl" in l for l in s.sent), s.sent


def test_fr4789_433_clears_mint_and_reconnects_for_sasl(tmp_path, monkeypatch):
    """433 on reserved nick with password present flips mint skip → SASL next."""
    (tmp_path / "console.password").write_text(
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n", encoding="utf-8"
    )
    (tmp_path / "console.password-minted").write_text("install\n", encoding="ascii")
    s = make(tmp_path, monkeypatch)
    assert s._nickserv_pw_minted is True
    s.handshake()
    s.sent.clear()
    s.logs.clear()
    s.on_line(":srv 433 * rm-sql01_console :Nickname is already in use")
    assert s._force_reconnect is True
    assert s._nickserv_pw_minted is False
    assert s._nickserv_account_known()
    assert not (tmp_path / "console.password-minted").is_file()
    assert any("FR #4789" in m for m in s.logs), s.logs
    assert not any(l.startswith("NICK rm-sql01_") and l != "NICK rm-sql01_console" for l in s.sent)
    # Next handshake must request SASL (upgrade / recover path).
    s._force_reconnect = False
    s.sent.clear()
    s.logs.clear()
    s.handshake()
    assert any(l.startswith("CAP REQ :") and "sasl" in l for l in s.sent), s.sent
    assert any("FR #3863" in m and "SASL" in m for m in s.logs) or any(
        "sasl" in l.lower() for l in s.sent
    )


def test_fr4789_433_after_account_known_stays_loud_error(tmp_path, monkeypatch):
    """When nickserv-ok exists, 433 remains the loud mismatch path (no mint recover)."""
    (tmp_path / "console.password").write_text(
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n", encoding="utf-8"
    )
    (tmp_path / "console.nickserv-ok").write_text("prior\n", encoding="ascii")
    s = make(tmp_path, monkeypatch)
    assert s._nickserv_account_known()
    s.on_line(":srv 433 * rm-sql01_console :Nickname is already in use")
    assert s._force_reconnect is True
    assert any(m.startswith("ERROR") and "NOT falling back" in m for m in s.logs), s.logs
    assert not any("FR #4789" in m for m in s.logs)


def test_fr4789_mark_nickserv_ok_atomic(tmp_path, monkeypatch):
    (tmp_path / "console.password").write_text(
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n", encoding="utf-8"
    )
    s = make(tmp_path, monkeypatch)
    s._mark_nickserv_ok("fr4789-atomic")
    marker = tmp_path / "console.nickserv-ok"
    assert marker.is_file()
    assert "fr4789-atomic" in marker.read_text(encoding="ascii")
    assert not (tmp_path / "console.nickserv-ok.tmp").is_file()
    assert not list(tmp_path.glob("*.nickserv-ok.tmp"))
    src = SERVICE.read_text(encoding="utf-8")
    assert "os.replace" in src
    assert "FR #4789" in src


def test_fr4789_keyboardinterrupt_reconnect_sleep_and_main(tmp_path, monkeypatch):
    src = SERVICE.read_text(encoding="utf-8")
    assert "FR #4789" in src
    assert "reconnect wait interrupted" in src or "reconnect interrupted" in src
    assert "except KeyboardInterrupt" in src.split("def main", 1)[1]
    # run() sleep during backoff must not escape as PYI unhandled.
    run_src = src.split("def run(self)", 1)[1].split("def build_arg_parser", 1)[0]
    assert "except KeyboardInterrupt" in run_src
    assert "time.sleep(backoff)" in run_src


def test_fr4789_reconnect_backoff_keyboardinterrupt_returns_0(tmp_path, monkeypatch):
    """NSSM stop during reconnect sleep must return 0, not raise."""
    (tmp_path / "console.password").write_text(
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n", encoding="utf-8"
    )
    s = make(tmp_path, monkeypatch)
    monkeypatch.setattr(s, "connect", lambda: (_ for _ in ()).throw(ConnectionError("offline")))
    monkeypatch.setattr(svc.time, "sleep", lambda _s: (_ for _ in ()).throw(KeyboardInterrupt()))
    stopped = []
    monkeypatch.setattr(s, "prepare_stop", lambda reason="": stopped.append(reason))
    assert s.run() == 0
    assert stopped == ["reconnect interrupted"]
    assert any("reconnect wait interrupted" in m for m in s.logs)


def test_fr4789_skill_pin():
    raw = SKILL.read_bytes()
    assert b"\xef\xbb\xbf" not in raw[:3]
    line = next(ln for ln in raw.splitlines() if b"FR #4789" in ln)
    assert b"airc_console_service.py" in line
    assert b"then 433 forever" in line
    assert b"`console.password-minted`" in line
    assert b"\x07" not in line
    assert b"\xc4\x9b" not in line
    assert b"irc_console_service.py" not in line.replace(b"airc_console_service.py", b"")
