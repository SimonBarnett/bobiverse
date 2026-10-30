"""FR #5196: a previous ear's quit request must not stop its replacement."""
from __future__ import annotations

import argparse
import os
from unittest.mock import Mock

import pytest

import agent_control
import irc_agent


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_HOME", str(tmp_path))
    monkeypatch.setenv("BOB_HOME_NO_MIGRATE", "1")
    monkeypatch.setattr(irc_agent.protect, "protect_path", lambda p: None)
    monkeypatch.setattr(irc_agent.bob_home, "ensure_homes", lambda **kw: [])
    args = argparse.Namespace(
        nick="Bob-test-5196", channel="#test-5196", home=str(tmp_path),
        host="irc.example", port=6697, password="", realname="test",
        outbox="", hello="", announce_key=False, once=True, chair=False,
        auto_nick=False,
    )
    return irc_agent.Client(args)


def test_old_request_removed_before_first_join(tmp_path, client):
    path = agent_control.quit_request_path(tmp_path)
    agent_control.request_agent_quit(tmp_path, "previous stop")
    old = client._process_started - 4.5 * 3600
    os.utime(path, (old, old))
    replacement = irc_agent.Client(client.args)
    assert not path.exists()
    replacement.joined.set()
    replacement.request_shutdown = Mock()
    assert not replacement._consume_control_quit()
    replacement.request_shutdown.assert_not_called()


@pytest.mark.parametrize("age", [0.01, 4.5 * 3600])
def test_pre_start_request_ignored_on_control_poll(client, age):
    path = agent_control.quit_request_path(client.home)
    agent_control.request_agent_quit(client.home, "previous stop")
    old = client._process_started - age
    os.utime(path, (old, old))
    client.joined.set()
    client.request_shutdown = Mock()
    assert not client._consume_control_quit()
    assert not path.exists()
    client.request_shutdown.assert_not_called()


def test_live_request_still_quits_gracefully(client):
    agent_control.request_agent_quit(client.home, "current stop")
    path = agent_control.quit_request_path(client.home)
    # Even within the startup second, a new file must not be discarded because
    # the protocol's embedded timestamp is only integer seconds.
    written = client._process_started + 0.01
    os.utime(path, (written, written))
    client.joined.set()
    client.request_shutdown = Mock()
    assert client._consume_control_quit()
    client.request_shutdown.assert_called_once_with(":control")
    assert not path.exists()
    assert not client._consume_control_quit()


def test_live_request_during_initialization_is_preserved(client, monkeypatch):
    path = agent_control.quit_request_path(client.home)

    def request_during_init(**kwargs):
        agent_control.request_agent_quit(client.home, "stop during init")

    monkeypatch.setattr(irc_agent.bob_home, "ensure_homes", request_during_init)
    replacement = irc_agent.Client(client.args)
    assert path.exists()
    replacement.request_shutdown = Mock()
    assert replacement._consume_control_quit()
    replacement.request_shutdown.assert_called_once_with(":control")


def test_live_request_before_client_construction_is_preserved(client):
    agent_control.request_agent_quit(client.home, "stop during startup checks")
    replacement = irc_agent.Client(client.args)
    assert replacement._process_started == client._process_started
    replacement.request_shutdown = Mock()
    assert replacement._consume_control_quit()
    replacement.request_shutdown.assert_called_once_with(":control")


def test_legacy_consumer_without_start_boundary(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_control.protect, "protect_path", lambda p: None)
    agent_control.request_agent_quit(tmp_path, "legacy stop")
    assert agent_control.peek_quit_request(tmp_path) == "legacy stop"
    assert agent_control.consume_quit_request(tmp_path) == "legacy stop"
    assert not agent_control.quit_request_path(tmp_path).exists()
