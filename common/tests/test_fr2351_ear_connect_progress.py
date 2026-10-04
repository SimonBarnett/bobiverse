"""FR #2351: bob-ear connect progress — irc.log on attempt, TLS timeout, bob-ear priors, --once exit."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from unittest import mock

import pytest

import irc_agent
import prior_irc


def test_script_kind_matches_bob_ear_exe():
    cmd = r'"C:\ai\test-msi\bob-admin\bob\scripts\bob-ear.exe" --nick ear-test --home C:\tmp\h'
    assert prior_irc.script_kind(cmd) == "irc_agent"


def test_select_victims_kills_other_bob_ear_same_nick():
    procs = [
        (100, r'"C:\x\bob-ear.exe" --nick ear-test-2351 --home C:\tmp\a'),
        (200, r'"C:\x\bob-ear.exe" --nick other --home C:\tmp\b'),
        (300, "python irc_agent.py --nick ear-test-2351 --home C:\\tmp\\c"),
    ]
    got = prior_irc.select_victims(procs, "ear-test-2351", r"C:\tmp\z", keep_pids={999})
    assert [(pid, kind) for pid, kind in got] == [(100, "irc_agent"), (300, "irc_agent")]


def test_select_victims_keeps_self_and_ancestors():
    procs = [
        (10, r'"C:\x\bob-ear.exe" --nick ear-test --home C:\tmp\h'),  # onefile parent
        (20, r'"C:\x\bob-ear.exe" --nick ear-test --home C:\tmp\h'),  # child = self
    ]
    # pretend 10 is ancestor of 20
    with mock.patch.object(prior_irc, "ancestor_pids", return_value={10}):
        got = prior_irc.select_victims(
            procs, "ear-test", r"C:\tmp\h", keep_pids={20}
        )
    assert got == []


def test_list_filter_patterns_include_bob_ear():
    # Source contract: Windows/posix listers must see frozen ear binaries.
    src = Path(prior_irc.__file__).read_text(encoding="utf-8")
    assert "bob-ear.exe" in src or "bob-ear" in src
    assert "ancestor_pids" in src


def test_connect_writes_irc_log_before_tcp(tmp_path, monkeypatch):
    home = tmp_path / "ear-home"
    home.mkdir()
    monkeypatch.setenv("BOB_IRC_DEBUG", "1")
    monkeypatch.setenv("BOB_HOME", str(home))
    monkeypatch.setenv("BOB_HOME_NO_MIGRATE", "1")
    monkeypatch.setenv("BOB_IRC_SKIP_PRIOR_CLEAN", "1")

    args = argparse.Namespace(
        nick="ear-test-2351",
        channel="#bob-ear-uat-2351",
        home=str(home),
        host="127.0.0.1",
        port=1,
        password="",
        realname="test",
        outbox="",
        hello="",
        announce_key=False,
        once=True,
        chair=False,
        auto_nick=False,
    )
    # Avoid protect_path / identity side effects slowing the unit test.
    monkeypatch.setattr(irc_agent.protect, "protect_path", lambda p: None)
    monkeypatch.setattr(irc_agent.bob_home, "ensure_homes", lambda **kw: [])
    c = irc_agent.Client(args)
    assert c.debug is not None
    assert Path(c.debug).is_file(), "irc.log must exist as soon as Client is constructed"
    text = Path(c.debug).read_text(encoding="utf-8")
    assert "debug-open" in text or "BOB_IRC_DEBUG" in text or "home=" in text

    calls = []

    def boom_connect(addr, timeout=None):
        calls.append((addr, timeout))
        # Prove connect() logged before TCP by checking file now.
        body = Path(c.debug).read_text(encoding="utf-8")
        assert "connecting" in body.lower() or "tcp" in body.lower()
        raise OSError("refused")

    monkeypatch.setattr(irc_agent.socket, "create_connection", boom_connect)
    with pytest.raises(OSError):
        c.connect()
    assert calls and calls[0][0] == ("127.0.0.1", 1)
    body = Path(c.debug).read_text(encoding="utf-8")
    assert "tcp" in body.lower() or "connect" in body.lower()


def test_once_session_returns_after_join(tmp_path, monkeypatch):
    home = tmp_path / "ear-home"
    home.mkdir()
    monkeypatch.setenv("BOB_IRC_DEBUG", "1")
    monkeypatch.setenv("BOB_HOME", str(home))
    monkeypatch.setenv("BOB_HOME_NO_MIGRATE", "1")
    monkeypatch.setattr(irc_agent.protect, "protect_path", lambda p: None)
    monkeypatch.setattr(irc_agent.bob_home, "ensure_homes", lambda **kw: [])

    args = argparse.Namespace(
        nick="ear-test-2351",
        channel="#bob-ear-uat-2351",
        home=str(home),
        host="irc.example",
        port=6697,
        password="",
        realname="test",
        outbox="",
        hello="",
        announce_key=False,
        once=True,
        chair=False,
        auto_nick=False,
    )
    c = irc_agent.Client(args)

    class FakeSock:
        def close(self):
            return None

        def recv(self, _n):
            import time

            time.sleep(0.05)
            return b""

    monkeypatch.setattr(c, "connect", lambda: FakeSock())
    monkeypatch.setattr(c, "send", lambda line: None)
    monkeypatch.setattr(c, "sasl_token", lambda: None)
    monkeypatch.setattr(c, "sasl_plain", lambda: False)
    monkeypatch.setattr(c, "_chair_oper_on_connect", lambda: None)
    monkeypatch.setattr(c, "_maybe_register_shop_chanserv", lambda: None)
    monkeypatch.setattr(c, "_local_machine_id", lambda: None)
    monkeypatch.setattr(c, "_seat_liveness_enabled", lambda: False)
    monkeypatch.setattr(c, "_chair_reset_session", lambda: None)

    # session() clears ready/joined at entry — trip them on wait.
    def _ready_wait(timeout=None):
        c.ready.set()
        return True

    def _joined_wait(timeout=None):
        c.joined.set()
        return True

    monkeypatch.setattr(c.ready, "wait", _ready_wait)
    monkeypatch.setattr(c.joined, "wait", _joined_wait)

    # If --once still spun forever, this would hang the test.
    c.session()
    assert c.args.once is True


def test_connect_source_has_ssl_timeout_and_debug_open():
    src = Path(irc_agent.__file__).read_text(encoding="utf-8")
    assert "FR #2351" in src
    assert "settimeout" in src
    assert "debug-open" in src or "irc.log" in src
    # --once must leave the post-JOIN loop.
    assert "once: session complete" in src or 'getattr(self.args, "once"' in src
