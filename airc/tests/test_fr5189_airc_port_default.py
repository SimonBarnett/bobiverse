from __future__ import annotations

import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

import airc_console_service as svc


def test_default_and_port_overrides(monkeypatch):
    monkeypatch.delenv("AIRC_IRC_PORT", raising=False)
    assert svc.build_arg_parser().parse_args([]).port == 993

    monkeypatch.setenv("AIRC_IRC_PORT", "6697")
    assert svc.build_arg_parser().parse_args([]).port == 6697
    assert svc.build_arg_parser().parse_args(["--port", "993"]).port == 993


@pytest.mark.parametrize(
    ("primary_port", "connect_error", "expected_ports"),
    [
        (993, socket.timeout("timed out"), [993, 6697]),
        (6697, ConnectionRefusedError(111, "connection refused"), [6697, 993]),
    ],
)
def test_connect_falls_back_between_ergo_tls_ports(
    monkeypatch, primary_port, connect_error, expected_ports
):
    attempts = []
    logs = []

    class FakeSocket:
        def settimeout(self, _timeout):
            pass

        def close(self):
            pass

    def create_connection(address, timeout):
        attempts.append((address, timeout))
        if len(attempts) == 1:
            raise connect_error
        return FakeSocket()

    monkeypatch.setattr(svc.socket, "create_connection", create_connection)
    monkeypatch.setattr(svc, "info", logs.append)

    service = svc.AircConsoleService.__new__(svc.AircConsoleService)
    service.args = SimpleNamespace(
        host="irc.ntsa.uk", port=primary_port, tls=False, tls_insecure=False
    )
    svc.AircConsoleService.connect(service)

    assert [address[1] for address, _timeout in attempts] == expected_ports
    assert service.connected_port == expected_ports[-1]
    assert any("connect-fallback" in line for line in logs)
    assert any(f"connected irc.ntsa.uk:{expected_ports[-1]}" in line for line in logs)


def test_connect_does_not_fallback_for_custom_port(monkeypatch):
    attempts = []

    def create_connection(address, timeout):
        attempts.append(address)
        raise socket.timeout("timed out")

    monkeypatch.setattr(svc.socket, "create_connection", create_connection)
    service = svc.AircConsoleService.__new__(svc.AircConsoleService)
    service.args = SimpleNamespace(host="irc.ntsa.uk", port=7000, tls=False, tls_insecure=False)

    with pytest.raises(socket.timeout):
        svc.AircConsoleService.connect(service)
    assert attempts == [("irc.ntsa.uk", 7000)]


def test_powerShell_launchers_use_environment_port_or_993():
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    expected_default = (
        "[int]$Port = $(if ($env:AIRC_IRC_PORT) "
        "{ [int]$env:AIRC_IRC_PORT } else { 993 }),"
    )
    for filename in (
        "Start-AircConsole.ps1",
        "Start-AircConsole-Fleet.ps1",
        "Start-AircConsoleSideBySide.ps1",
    ):
        assert expected_default in (scripts / filename).read_text(encoding="utf-8-sig")
