"""#34: registered-shop console must not fall back to {machine}_N, must be loud on SASL failure,
and must not JOIN under a nick the server did not confirm."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import airc_console_service as svc

S = Path(__file__).resolve().parent.parent / "scripts"


def make(tmp_path, monkeypatch, extra=()):
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "x-server-pass")
    args = svc.build_arg_parser().parse_args(
        ["--machine", "tm", "--home", str(tmp_path), "--shop-mode", "registered",
         "--operators", "op", *extra]
    )
    s = svc.AircConsoleService(args)
    s.sent = []
    s.send = lambda line: s.sent.append(line)  # type: ignore[assignment]
    s.logs = []
    monkeypatch.setattr(svc, "info", lambda m: s.logs.append(m))
    return s


def test_433_on_reserved_nick_does_not_fall_back_or_register(tmp_path, monkeypatch):
    s = make(tmp_path, monkeypatch)
    s.handshake()
    s.sent.clear()
    s.on_line(":srv 433 * tm_console :Nickname is already in use")
    assert not any(l.startswith("NICK tm_") and l != "NICK tm_console" for l in s.sent), s.sent
    assert not any("REGISTER" in l for l in s.sent)
    assert s._force_reconnect is True
    assert any(m.startswith("ERROR") and "NOT falling back" in m for m in s.logs)


def test_sasl_904_is_loud_error(tmp_path, monkeypatch):
    s = make(tmp_path, monkeypatch)
    s.on_line(":srv 904 * :SASL authentication failed")
    assert any(m.startswith("ERROR console account tm_console SASL failed") for m in s.logs)
    assert s._sasl_failed


def test_no_register_of_machine_n_accounts_in_shop_mode(tmp_path, monkeypatch):
    s = make(tmp_path, monkeypatch)
    s._set_nick("tm_5")
    s.sent.clear()
    s.register_or_identify()
    assert s.sent == []
    assert any("refusing NickServ REGISTER" in m for m in s.logs)
    s._set_nick("tm_console")
    s.register_or_identify()
    assert any("REGISTER" in l for l in s.sent)


def test_join_deferred_when_server_nick_differs(tmp_path, monkeypatch):
    s = make(tmp_path, monkeypatch)
    s.handshake()
    s.sent.clear()
    # server welcomed us under a different nick than we want
    s.on_line(":srv 001 tm_5 :Welcome")
    assert not any(l.startswith("JOIN") for l in s.sent), s.sent
    assert any("not joining" in m for m in s.logs)
    assert s.logs and s._joined_shop is False


def test_join_happens_when_server_confirms_nick(tmp_path, monkeypatch):
    s = make(tmp_path, monkeypatch)
    s.handshake()
    s.sent.clear()
    s.on_line(":srv 001 tm_console :Welcome")
    assert any(l.startswith("JOIN") and "#tm" in l for l in s.sent), s.sent
    assert s._joined_shop is True


def test_join_after_own_nick_echo(tmp_path, monkeypatch):
    s = make(tmp_path, monkeypatch)
    s.handshake()
    s.on_line(":srv 001 tm_5 :Welcome")
    s.sent.clear()
    s.on_line(":tm_5!u@h NICK :tm_console")
    assert s.server_nick == "tm_console"
    assert any(l.startswith("JOIN") for l in s.sent), s.sent


def test_no_sasl_in_shop_mode_logs_error(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "x")
    logs = []
    monkeypatch.setattr(svc, "info", lambda m: logs.append(m))
    args = svc.build_arg_parser().parse_args(
        ["--machine", "tm", "--home", str(tmp_path), "--shop-mode", "registered",
         "--operators", "op", "--no-sasl"]
    )
    svc.AircConsoleService(args)
    assert any(m.startswith("ERROR --no-sasl") for m in logs)


def test_start_script_passes_sasl_choice_explicitly():
    t = (S / "Start-AircConsole.ps1").read_text(encoding="utf-8-sig")
    assert "$argsList += '--sasl'" in t
    assert "$argsList += '--no-sasl'" in t
