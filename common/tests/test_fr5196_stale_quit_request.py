"""FR #5196: a stopped ear's control file must not stop its replacement."""
from __future__ import annotations

import argparse
import os
from unittest.mock import Mock

import pytest

import agent_control
import irc_agent


@pytest.fixture
def ear(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_HOME", str(tmp_path))
    monkeypatch.setenv("BOB_HOME_NO_MIGRATE", "1")
    monkeypatch.delenv("BOB_IRC_DEBUG", raising=False)
    monkeypatch.setattr(irc_agent.protect, "protect_path", lambda path: None)
    monkeypatch.setattr(irc_agent.bob_home, "ensure_homes", lambda **kwargs: [])
    args = argparse.Namespace(
        nick="Bob-test", channel="#test", home=str(tmp_path), outbox="", chair=False,
    )
    client = irc_agent.Client(args)
    client.request_shutdown = Mock()
    return client


@pytest.mark.parametrize("contents", ["old-stop", ""])
def test_stale_request_is_removed_without_shutdown(ear, contents):
    agent_control.request_agent_quit(ear.home, "old-stop")
    path = agent_control.quit_request_path(ear.home)
    if not contents:
        path.write_text("", encoding="utf-8")
    old = ear._process_started - 4.5 * 3600
    os.utime(path, (old, old))

    assert ear._consume_control_quit() is False
    assert not path.exists()
    assert not ear.stop.is_set()
    ear.request_shutdown.assert_not_called()
    assert ear._consume_control_quit() is False


def test_live_request_still_quits_gracefully_in_startup_second(ear):
    agent_control.request_agent_quit(ear.home, "new-stop")
    path = agent_control.quit_request_path(ear.home)
    # The payload's integer seconds can predate startup even for a live request.
    path.write_text(f"{int(ear._process_started)} new-stop\n", encoding="utf-8")
    written = ear._process_started + 0.01
    os.utime(path, (written, written))

    assert ear._consume_control_quit() is True
    assert not path.exists()
    ear.request_shutdown.assert_called_once_with(":control")
    assert ear._consume_control_quit() is False


def test_stale_then_live_request(ear):
    agent_control.request_agent_quit(ear.home, "old-stop")
    path = agent_control.quit_request_path(ear.home)
    old = ear._process_started - 60
    os.utime(path, (old, old))
    assert ear._consume_control_quit() is False

    agent_control.request_agent_quit(ear.home, "restart")
    written = ear._process_started + 1
    os.utime(path, (written, written))
    assert ear._consume_control_quit() is True
    ear.request_shutdown.assert_called_once_with(":control")


def test_reconnect_does_not_make_a_live_request_stale(ear):
    agent_control.request_agent_quit(ear.home, "restart")
    path = agent_control.quit_request_path(ear.home)
    written = ear._process_started + 1
    os.utime(path, (written, written))
    ear._irc_session_started = written + 60

    assert ear._consume_control_quit() is True
    ear.request_shutdown.assert_called_once_with(":control")


def test_unfiltered_consumer_remains_compatible(tmp_path):
    agent_control.request_agent_quit(tmp_path, "legacy-stop")
    assert agent_control.peek_quit_request(tmp_path) == "legacy-stop"
    assert agent_control.consume_quit_request(tmp_path) == "legacy-stop"
    assert agent_control.consume_quit_request(tmp_path) is None
