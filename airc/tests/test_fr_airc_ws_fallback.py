"""FR #7999: ordered transport selection, TLS-reset -> WSS fallback, registration log."""
from __future__ import annotations

import argparse
import socket
import struct
import threading
from pathlib import Path
from types import SimpleNamespace

import airc_console_service as svc


def _ns(**kw):
    return argparse.Namespace(**kw)


def test_resolve_irc_transports_default_tls_first():
    args = _ns(transport=None, ws_url=None, port=993)
    assert svc.resolve_irc_transports(args) == [
        ("tls", 993),
        ("tls", 6697),
        ("wss", svc.DEFAULT_IRC_WS_URL),
    ]


def test_resolve_irc_transports_configured_tls_first():
    args = _ns(transport="tls,wss", ws_url="ws://127.0.0.1:1/", port=6697)
    assert svc.resolve_irc_transports(args) == [
        ("tls", 6697),
        ("tls", 993),
        ("wss", "ws://127.0.0.1:1/"),
    ]


def test_resolve_irc_transports_skips_empty_wss():
    args = _ns(transport="wss,tls", ws_url="", port=993)
    assert svc.resolve_irc_transports(args) == [("tls", 993), ("tls", 6697)]


def test_resolve_irc_transports_dedupes():
    args = _ns(transport="wss,tls,wss", ws_url="ws://127.0.0.1:1/", port=993)
    assert svc.resolve_irc_transports(args) == [
        ("wss", "ws://127.0.0.1:1/"),
        ("tls", 993),
        ("tls", 6697),
    ]


def test_validate_transport_config():
    assert svc.validate_transport_config(_ns(transport="wss,tls", ws_url="wss://x.example/")) is None
    assert svc.validate_transport_config(_ns(transport="tls", ws_url="")) is None
    assert "bogus" in svc.validate_transport_config(_ns(transport="wss,bogus", ws_url=""))
    assert svc.validate_transport_config(_ns(transport="", ws_url=""))  # empty -> error
    assert svc.validate_transport_config(_ns(transport="wss", ws_url="http://x/"))  # bad scheme
    assert svc.validate_transport_config(_ns(transport="wss", ws_url="wss://u:p@x/"))  # userinfo


def test_argparse_defaults(monkeypatch):
    monkeypatch.delenv("AIRC_IRC_TRANSPORT", raising=False)
    monkeypatch.delenv("AIRC_IRC_WS_URL", raising=False)
    args = svc.build_arg_parser().parse_args([])
    assert args.transport == "tls,wss"
    assert args.ws_url == "wss://wsirc.ntsa.uk"


def test_argparse_cli_overrides_env(monkeypatch):
    monkeypatch.setenv("AIRC_IRC_TRANSPORT", "wss,tls")
    args = svc.build_arg_parser().parse_args(["--transport", "tls"])
    assert args.transport == "tls"


def test_run_exits_2_on_invalid_transport(monkeypatch, tmp_path):
    monkeypatch.setattr(svc, "info", lambda _m: None)
    s = svc.AircConsoleService.__new__(svc.AircConsoleService)
    s.home = Path(tmp_path)
    s.machine = "tm"
    s.channel = "#tm"
    s.nick = "tm_console"
    s.server_password = "x"
    s.args = _ns(
        host="irc.ntsa.uk", port=993, tls=True, tls_insecure=False,
        transport="bogus", ws_url="",
    )
    assert svc.AircConsoleService.run(s) == 2


def _start_reset_listener():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)
    port = int(srv.getsockname()[1])
    stop = threading.Event()

    def _run():
        srv.settimeout(5.0)
        while not stop.is_set():
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            except OSError:
                pass
            conn.close()

    threading.Thread(target=_run, daemon=True).start()
    return port, srv, stop


class _FakeWsTransport:
    def __init__(self, label: str):
        self.label = label
        self.closed = False

    def settimeout(self, value) -> None:
        pass

    def close(self) -> None:
        self.closed = True


def test_connect_reset_tls_falls_back_to_wss(monkeypatch):
    port, srv, stop = _start_reset_listener()
    try:
        made = {}

        def fake_connect_ws(url, timeout=30, verify=True):
            t = _FakeWsTransport(url)
            made["url"] = url
            made["timeout"] = timeout
            made["verify"] = verify
            return t

        monkeypatch.setattr(svc._ws, "connect_ws", fake_connect_ws)
        args = _ns(
            host="127.0.0.1", port=port, tls=True, tls_insecure=False,
            transport="tls,wss", ws_url="ws://127.0.0.1:1/",
        )
        console = svc.AircConsoleService.__new__(svc.AircConsoleService)
        console.args = args
        console.sock = None
        console._transport_desc = None
        console._transport_logged = False
        console.connect()
        assert console._transport_desc == "wss ws://127.0.0.1:1/"
        assert made["url"] == "ws://127.0.0.1:1/"
        assert console.sock is not None
        assert console.sock.closed is False
        console.sock.close()
    finally:
        stop.set()
        srv.close()


def test_connect_tls_working_default_never_tries_wss(monkeypatch):
    """FR #7999 acceptance: with TLS ports working, airc never tries WSS first."""
    calls = {"ws": 0}

    class _TlsSock:
        def settimeout(self, value):
            pass
        def close(self):
            pass

    def fake_create(addr, timeout=30):
        return _TlsSock()

    class _Ctx:
        check_hostname = True
        verify_mode = 0
        def wrap_socket(self, raw, server_hostname=None):
            return raw

    def fail_ws(url, timeout=30, verify=True):
        calls["ws"] += 1
        raise AssertionError("WSS must not be tried when TLS succeeds on default order")

    monkeypatch.setattr(svc.socket, "create_connection", fake_create)
    monkeypatch.setattr(svc.ssl, "create_default_context", lambda: _Ctx())
    monkeypatch.setattr(svc._ws, "connect_ws", fail_ws)
    monkeypatch.setattr(svc, "info", lambda _m: None)
    args = _ns(
        host="127.0.0.1", port=993, tls=True, tls_insecure=False,
        transport=None, ws_url=None,
    )
    console = svc.AircConsoleService.__new__(svc.AircConsoleService)
    console.args = args
    console.sock = None
    console._transport_desc = None
    console._transport_logged = False
    console.connect()
    assert console._transport_desc == "tls 127.0.0.1:993"
    assert calls["ws"] == 0
    console.sock.close()


def test_connect_tls_first_configured_never_tries_wss(monkeypatch):
    # a listening socket that accepts so create_connection succeeds (tls=False)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = int(srv.getsockname()[1])
    try:
        def fail_connect_ws(url, timeout=30, verify=True):
            raise AssertionError("WSS must not be tried when TLS succeeds first")

        monkeypatch.setattr(svc._ws, "connect_ws", fail_connect_ws)
        args = _ns(
            host="127.0.0.1", port=port, tls=False, tls_insecure=False,
            transport="tls,wss", ws_url="ws://127.0.0.1:1/",
        )
        console = svc.AircConsoleService.__new__(svc.AircConsoleService)
        console.args = args
        console.sock = None
        console._transport_desc = None
        console._transport_logged = False
        console.connect()
        assert console._transport_desc == f"tls 127.0.0.1:{port}"
        console.sock.close()
    finally:
        srv.close()


def test_001_logs_registered_transport_once(monkeypatch):
    lines: list[str] = []
    monkeypatch.setattr(svc, "info", lambda m: lines.append(m))
    s = svc.AircConsoleService.__new__(svc.AircConsoleService)
    s._last_recv = 0.0
    s._transport_desc = "wss ws://127.0.0.1:1/"
    s._transport_logged = False
    s._registered = False
    s._nick_retries = 0
    s.server_nick = None
    s.shop_mode = "registered"
    s._apply_shop_mode = lambda mode: None
    s.members = None
    s.auth_mode = "irc_ops"
    s.core = SimpleNamespace(handle_raw=lambda _l: None)
    s._on_line_unguarded(":srv 001 nick :Welcome")
    assert s._registered is True
    assert any("registered via transport=wss ws://127.0.0.1:1/" in l for l in lines)
    s._on_line_unguarded(":srv 001 nick :Welcome")
    assert sum("registered via transport=" in l for l in lines) == 1
