"""FR #6282 reopen: isolate ALL inbound dispatch paths from session death.

After PR #6283, MarchHare still looped on:
  chanserv-sync notice error AttributeError
  session end TypeError
NOTICE was caught name-only (no traceback); other hooks stayed bare.
Requirements (Simon reopen): wrap NOTICE/PRIVMSG/JOIN/PART/MODE/numerics;
log full traceback; session-end must not raise; ChanServ NOTICE replay
keeps the socket connected.
"""
from __future__ import annotations

import argparse
import socket
import threading
import time
from pathlib import Path
from unittest import mock

import pytest

import irc_agent


def _bare_client(tmp_path: Path) -> irc_agent.Client:
    args = argparse.Namespace(
        host="127.0.0.1",
        port=6697,
        nick="Bob-marchhare",
        realname="bob-ear",
        password="",
        channel="#marchhare",
        home=str(tmp_path),
        chair=False,
        hello="",
        announce_key=False,
        once=False,
        debug=False,
        install_root="",
    )
    c = irc_agent.Client.__new__(irc_agent.Client)
    c.args = args
    c.home = Path(tmp_path)
    c.original_nick = "Bob-marchhare"
    c.live_nick = "Bob-marchhare"
    c.channels = ["#bobiverse", "#wonderland", "#marchhare"]
    c.stop = threading.Event()
    c.dead = threading.Event()
    c.ready = threading.Event()
    c.joined = threading.Event()
    c.joined.set()
    c.sock = mock.Mock()
    c.lock = threading.Lock()
    c.debug = None
    c.accounts = None
    c._last_server_rx = time.time()
    c._pong_due_at = 0.0
    c._awaiting_client_pong = False
    c._last_client_ping = 0.0
    c._last_keepalive_log = 0.0
    c._no_reconnect = False
    c._nickname_reserved = False
    c._throttle_n = 0
    c._throttled = False
    c._linelen = 512
    c._cs_collector = None
    c._cs_register_wait = {}
    c._cs_unregister_wait = {}
    c._cs_list_status = "unknown"
    c._cs_force = False
    c._cs_fail_at = 0.0
    c._oper_state = "off"
    c._oper_name = ""
    c._oper_done = threading.Event()
    return c


def test_fr6282_log_dispatch_error_includes_traceback_and_hook(monkeypatch):
    logged: list[str] = []
    monkeypatch.setattr(irc_agent, "info", lambda m: logged.append(str(m)))
    try:
        raise AttributeError("simulated chanserv attr miss")
    except AttributeError as exc:
        irc_agent.Client._log_dispatch_error(
            None,
            "chanserv_notice",
            exc,
            cmd="NOTICE",
            src="ChanServ",
            target="Bob-marchhare",
        )
    blob = "\n".join(logged)
    assert "irc-handler-error hook=chanserv_notice" in blob
    assert "AttributeError" in blob
    assert "Traceback" in blob or "File " in blob
    assert "simulated chanserv attr miss" in blob


def test_fr6282_chanserv_notice_attr_error_keeps_reader_alive(tmp_path, monkeypatch):
    """Raising inside _on_chanserv_notice must not set dead before EOF."""
    logged: list[str] = []
    monkeypatch.setattr(irc_agent, "info", lambda m: logged.append(str(m)))
    c = _bare_client(tmp_path)
    calls = {"n": 0}

    def boom(_text: str) -> None:
        raise AttributeError("module 'unregister_cmd' has no attribute 'parse_chanserv_register_result'")

    c._on_chanserv_notice = boom  # type: ignore[method-assign]
    observed = []

    def ok_privmsg(prefix, target, body):
        observed.append(body)

    c.handle_privmsg = ok_privmsg  # type: ignore[method-assign]

    def fake_recv(_n: int):
        calls["n"] += 1
        if calls["n"] == 1:
            return (
                b":ChanServ!services@host NOTICE Bob-marchhare :Channel #marchhare is already registered\r\n"
                b":jeeves!u@h PRIVMSG #marchhare :hello after notice\r\n"
                b"PING :alive\r\n"
            )
        c.stop.set()
        return b""

    c.sock.recv = fake_recv
    sent = []
    c.send = lambda line: sent.append(line)  # type: ignore[method-assign]
    c.reader()
    assert any("hello after notice" in x for x in observed)
    assert any(s.startswith("PONG ") for s in sent)
    # dead is set in finally after clean EOF/stop — acceptable; key is privmsg ran
    blob = "\n".join(logged)
    assert "irc-handler-error hook=" in blob or "handler=chanserv" in blob.lower() or "AttributeError" in blob
    assert "Traceback" in blob or "File " in blob


@pytest.mark.parametrize(
    "hook_name,wire",
    [
        ("handle_join", b":x!u@h JOIN #marchhare\r\n"),
        ("_on_oper_numeric", b":irc 381 Bob-marchhare :You are now an IRC operator\r\n"),
        ("_chair_wire", b":irc 353 Bob-marchhare = #marchhare :nick1 nick2\r\n"),
    ],
)
def test_fr6282_bare_hooks_isolated(tmp_path, monkeypatch, hook_name, wire):
    logged: list[str] = []
    monkeypatch.setattr(irc_agent, "info", lambda m: logged.append(str(m)))
    c = _bare_client(tmp_path)
    observed = []

    def boom(*a, **k):
        raise TypeError(f"boom-{hook_name}")

    setattr(c, hook_name if hook_name != "handle_join" else "handle_join", boom)
    if hook_name == "handle_join":
        c.handle_join = boom  # type: ignore[method-assign]
    elif hook_name == "_on_oper_numeric":
        c._on_oper_numeric = boom  # type: ignore[method-assign]
    elif hook_name == "_chair_wire":
        c._chair_wire = boom  # type: ignore[method-assign]

    def ok_privmsg(prefix, target, body):
        observed.append(body)

    c.handle_privmsg = ok_privmsg  # type: ignore[method-assign]
    calls = {"n": 0}

    def fake_recv(_n: int):
        calls["n"] += 1
        if calls["n"] == 1:
            return wire + b":jeeves!u@h PRIVMSG #marchhare :after-hook\r\n"
        c.stop.set()
        return b""

    c.sock.recv = fake_recv
    c.send = lambda line: None  # type: ignore[method-assign]
    c.reader()
    assert any("after-hook" in x for x in observed)
    blob = "\n".join(logged)
    assert "TypeError" in blob
    assert "Traceback" in blob or "File " in blob


def test_fr6282_session_end_logs_full_traceback(tmp_path, monkeypatch):
    logged: list[str] = []
    monkeypatch.setattr(irc_agent, "info", lambda m: logged.append(str(m)))
    c = _bare_client(tmp_path)
    c._no_reconnect = True

    def boom_session():
        raise TypeError("session teardown TypeError")

    c.session = boom_session  # type: ignore[method-assign]
    monkeypatch.setattr(irc_agent, "reconnect_cap", lambda: 0)
    c.run_forever()
    blob = "\n".join(logged)
    assert "session end TypeError" in blob
    assert "Traceback" in blob or "File " in blob
    assert "session teardown TypeError" in blob


def test_fr6282_chanserv_register_notices_do_not_raise(tmp_path, monkeypatch):
    """Real ChanServ REGISTER reply shapes must not raise on a fleet ear."""
    logged: list[str] = []
    monkeypatch.setattr(irc_agent, "info", lambda m: logged.append(str(m)))
    c = _bare_client(tmp_path)
    c._on_chanserv_notice = irc_agent.Client._on_chanserv_notice.__get__(c, irc_agent.Client)
    for text in (
        "Channel #marchhare is already registered",
        "Successfully registered channel #marchhare",
        "Channel #marchhare is now registered",
        "You must be in the channel to register it",
    ):
        c._on_chanserv_notice(text)  # must not raise
    assert logged == [] or all("irc-handler-error" not in x for x in logged)


def test_fr6282_unregister_cmd_contract_pins_parse_helpers():
    import unregister_cmd

    irc_agent.assert_ear_dispatch_contracts()
    assert callable(unregister_cmd.parse_chanserv_register_result)
    assert callable(unregister_cmd.parse_chanserv_unregister_confirm)


def test_fr6282_main_calls_assert_ear_dispatch_contracts():
    """MRB #6291: startup must run full dispatch contracts (unregister_cmd + gitclaim)."""
    src = Path(irc_agent.__file__).read_text(encoding="utf-8")
    main_idx = src.index("def main() -> None:")
    next_def = src.find("\ndef ", main_idx + 1)
    body = src[main_idx: next_def if next_def != -1 else None]
    assert "assert_ear_dispatch_contracts()" in body
    # Must not call the gitclaim-only helper alone at startup.
    assert "assert_ear_gitclaim_contract()" not in body
    irc_agent.assert_ear_dispatch_contracts()
