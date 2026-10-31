"""FR #5188 / #5189: airc defaults to TLS 993; 6697 remains override + fallback."""
from __future__ import annotations

import argparse
import errno
import socket
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import airc_console_service as svc  # noqa: E402


def test_resolve_irc_ports_default_then_6697():
    assert svc.resolve_irc_ports(993) == [993, 6697]


def test_resolve_irc_ports_explicit_6697_then_993():
    assert svc.resolve_irc_ports(6697) == [6697, 993]


def test_resolve_irc_ports_custom_then_both_tls():
    assert svc.resolve_irc_ports(7000) == [7000, 993, 6697]


def test_argparse_default_port_is_993(monkeypatch):
    monkeypatch.delenv("AIRC_IRC_PORT", raising=False)
    args = svc.build_arg_parser().parse_args([])
    assert args.port == 993


def test_argparse_env_override_6697(monkeypatch):
    monkeypatch.setenv("AIRC_IRC_PORT", "6697")
    args = svc.build_arg_parser().parse_args([])
    assert args.port == 6697


def test_start_scripts_default_993():
    roots = Path(__file__).resolve().parents[1] / "scripts"
    for name in (
        "Start-AircConsole.ps1",
        "Start-AircConsole-Fleet.ps1",
        "Start-AircConsoleSideBySide.ps1",
    ):
        text = (roots / name).read_text(encoding="utf-8")
        assert "[int]$Port = 993" in text, name
        assert "[int]$Port = 6697" not in text, name


def test_connect_falls_back_after_993_timeout(monkeypatch):
    calls: list[int] = []

    def fake_create(addr, timeout=30):
        host, port = addr
        calls.append(int(port))
        if int(port) == 993:
            err = OSError(errno.ETIMEDOUT, "timed out")
            err.winerror = 10060
            raise err
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        return sock

    monkeypatch.setattr(svc.socket, "create_connection", fake_create)
    args = argparse.Namespace(
        host="irc.example.test",
        port=993,
        tls=False,
        tls_insecure=False,
        home="unused",
    )
    console = svc.AircConsoleService.__new__(svc.AircConsoleService)
    console.args = args
    console.sock = None
    console.connect()
    assert calls == [993, 6697]
    assert console.args.port == 6697
    assert console.sock is not None
    console.sock.close()
