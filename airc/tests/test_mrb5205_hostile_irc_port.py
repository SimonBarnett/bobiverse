"""MRB #5205 hostile pins: default 993, refuse then other TLS port, skill 10060."""
from __future__ import annotations

import argparse
import errno
import socket

import airc_console_service as svc
from repo_layout import ROOT


def test_mrb5205_default_and_fallback_tuple():
    assert svc.DEFAULT_IRC_PORT == 993
    assert svc.FALLBACK_IRC_PORTS == (993, 6697)
    assert svc.resolve_irc_ports(993)[0] == 993
    src = (ROOT / "airc" / "scripts" / "airc_console_service.py").read_text(encoding="utf-8")
    assert src.index("DEFAULT_IRC_PORT = 993") < src.index("build_arg_parser")
    skill = (
        ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-troubleshooting" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "FR #5188" in skill
    assert "993" in skill
    assert "10060" in skill
    assert not (
        ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-troubleshooting" / "SKILL.md"
    ).read_bytes().startswith(b"\xef\xbb\xbf")


def test_mrb5205_connect_falls_back_on_connrefused(monkeypatch):
    calls: list[int] = []

    def fake_create(addr, timeout=30):
        _host, port = addr
        calls.append(int(port))
        if int(port) == 993:
            raise OSError(errno.ECONNREFUSED, "refused")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        return sock

    monkeypatch.setattr(svc.socket, "create_connection", fake_create)
    console = svc.AircConsoleService.__new__(svc.AircConsoleService)
    console.args = argparse.Namespace(host="irc.example.test", port=993, tls=False, tls_insecure=False)
    console.sock = None
    console.connect()
    assert calls == [993, 6697]
    assert console.args.port == 6697
    assert console.sock is not None
    console.sock.close()
