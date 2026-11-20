"""FR #8009: airc.exe connect self-test classifies reset, TLS, and a healthy read."""
from __future__ import annotations

import socket
import ssl

import airc_connect_probe as probe


class _Sock:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True

    def recv(self, _n):
        return b":irc.example 001 bot :Welcome\r\n"

    def settimeout(self, _t):
        return None


def test_rst_before_bytes_is_local_reset_and_prints_diagnosis():
    def connector(_h, _p, _t):
        return _Sock()

    def wrapper(_raw, _host):
        err = ConnectionResetError(10054, "connection reset")
        err.winerror = 10054
        raise err

    out = probe.probe_connection(
        "irc.example", 6697, tls=True, connector=connector, wrapper=wrapper
    )
    assert out["kind"] == probe.CLASS_LOCAL_RESET
    assert "local reset" in out["detail"]
    assert "airc.exe" in out["diagnosis"]
    assert probe.RULE_NAME in out["diagnosis"]
    assert "Do not disable Defender" in out["diagnosis"]


def test_tls_alert_is_tls_error_with_reason():
    def connector(_h, _p, _t):
        return _Sock()

    def wrapper(_raw, _host):
        raise ssl.SSLError("tlsv1 alert handshake failure")

    out = probe.probe_connection(
        "irc.example", 6697, tls=True, connector=connector, wrapper=wrapper
    )
    assert out["kind"] == probe.CLASS_TLS
    assert "tlsv1 alert handshake failure" in out["detail"]
    assert "diagnosis" not in out


def test_healthy_server_passes_with_no_writes():
    writes = []

    def connector(_h, _p, _t):
        return _Sock()

    def wrapper(raw, _host):
        return raw

    def reader(_sock):
        return b":irc.example 001 bot :Welcome\r\n"

    out = probe.probe_connection(
        "irc.example",
        6697,
        tls=True,
        connector=connector,
        wrapper=wrapper,
        reader=reader,
    )
    assert out["kind"] == probe.CLASS_OK
    assert writes == []
    assert out["bytes_sent"] == 0


def test_allow_rule_is_added_once_and_removed():
    calls = []

    def runner(argv):
        calls.append(list(argv))
        if argv[3] == "show":
            if any(c[3] == "add" for c in calls[:-1]):
                return f"Rule Name: {probe.RULE_NAME}"
            return "No rules match the specified criteria."
        return "Ok."

    assert probe.ensure_allow_rule(r"C:\airc\airc.exe", "irc.example", 6697, runner) is True
    assert probe.ensure_allow_rule(r"C:\airc\airc.exe", "irc.example", 6697, runner) is False
    adds = [c for c in calls if c[3] == "add"]
    assert len(adds) == 1
    probe.remove_allow_rule(runner)
    assert calls[-1][3] == "delete"
    assert any(probe.RULE_NAME in part for part in calls[-1])


def test_dns_and_timeout_classes():
    assert probe.classify_connect_error(socket.gaierror(8, "no name"), bytes_sent=0) == probe.CLASS_DNS
    err = TimeoutError("timed out")
    assert probe.classify_connect_error(err, bytes_sent=0) == probe.CLASS_TCP_TIMEOUT
    assert "network firewall" in probe.format_class(probe.CLASS_TCP_TIMEOUT)
