"""FR #5189: Airc defaults to TLS 993 and retains 6697 as an override/fallback."""
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


class FakeTLSContext:
    def wrap_socket(self, sock, server_hostname):
        return sock


def stub_tls(monkeypatch):
    contexts = []

    def create_context():
        context = FakeTLSContext()
        contexts.append(context)
        return context

    monkeypatch.setattr(svc.ssl, "create_default_context", create_context)
    return contexts


def test_argparse_default_port_is_993(monkeypatch):
    monkeypatch.delenv("AIRC_IRC_PORT", raising=False)
    assert svc.build_arg_parser().parse_args([]).port == 993


def test_argparse_env_and_cli_port_overrides(monkeypatch):
    monkeypatch.setenv("AIRC_IRC_PORT", "6697")
    parser = svc.build_arg_parser()
    assert parser.parse_args([]).port == 6697
    assert parser.parse_args(["--port", "993"]).port == 993


def test_resolve_irc_ports_tries_alternate_tls_listener():
    assert svc.resolve_irc_ports(993) == (993, 6697)
    assert svc.resolve_irc_ports(6697) == (6697, 993)
    assert svc.resolve_irc_ports(7000) == (7000,)
    assert svc.resolve_irc_ports(993, tls=False) == (993,)


def test_start_scripts_use_environment_override_and_default_993():
    roots = Path(__file__).resolve().parents[1] / "scripts"
    for name in (
        "Start-AircConsole.ps1",
        "Start-AircConsole-Fleet.ps1",
        "Start-AircConsoleSideBySide.ps1",
    ):
        text = (roots / name).read_text(encoding="utf-8-sig")
        assert "[int]$Port = $(if ($env:AIRC_IRC_PORT)" in text, name
        assert "else { 993 })" in text, name
        assert "[int]$Port = 6697" not in text, name


def test_connect_falls_back_to_6697_after_timeout(monkeypatch):
    calls: list[int] = []
    opened: list[socket.socket] = []

    def fake_create_connection(addr, timeout=30):
        _, port = addr
        calls.append(port)
        if port == 993:
            raise socket.timeout("timed out")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        opened.append(sock)
        return sock

    monkeypatch.setattr(svc.socket, "create_connection", fake_create_connection)
    tls_contexts = stub_tls(monkeypatch)
    console = svc.AircConsoleService.__new__(svc.AircConsoleService)
    console.args = argparse.Namespace(host="irc.example.test", port=993, tls=True, tls_insecure=False)
    console.sock = None
    console.connect()

    assert calls == [993, 6697]
    assert tls_contexts[0].minimum_version == svc.ssl.TLSVersion.TLSv1_2
    assert console.args.port == 6697
    assert console.sock is opened[0]
    console.sock.close()


def test_connect_falls_back_to_993_after_6697_refusal(monkeypatch):
    calls: list[int] = []
    opened: list[socket.socket] = []

    def fake_create_connection(addr, timeout=30):
        _, port = addr
        calls.append(port)
        if port == 6697:
            raise ConnectionRefusedError(errno.ECONNREFUSED, "refused")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        opened.append(sock)
        return sock

    monkeypatch.setattr(svc.socket, "create_connection", fake_create_connection)
    stub_tls(monkeypatch)
    console = svc.AircConsoleService.__new__(svc.AircConsoleService)
    console.args = argparse.Namespace(host="irc.example.test", port=6697, tls=True, tls_insecure=False)
    console.sock = None
    console.connect()

    assert calls == [6697, 993]
    assert console.args.port == 993
    assert console.sock is opened[0]
    console.sock.close()


def test_connect_does_not_fallback_for_other_errors(monkeypatch):
    calls: list[int] = []

    def fake_create_connection(addr, timeout=30):
        calls.append(addr[1])
        raise OSError(errno.EHOSTUNREACH, "host unreachable")

    monkeypatch.setattr(svc.socket, "create_connection", fake_create_connection)
    console = svc.AircConsoleService.__new__(svc.AircConsoleService)
    console.args = argparse.Namespace(host="irc.example.test", port=993, tls=True, tls_insecure=False)
    console.sock = None

    try:
        console.connect()
    except OSError as exc:
        assert exc.errno == errno.EHOSTUNREACH
    else:
        raise AssertionError("connect should propagate non-fallback errors")
    assert calls == [993]
