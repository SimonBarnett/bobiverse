"""FR #5196: a previous process's quit request must not stop a restarted ear."""
from __future__ import annotations

import os
from unittest.mock import Mock

import pytest

import agent_control
import irc_agent


@pytest.fixture
def ear(tmp_path):
    client = irc_agent.Client.__new__(irc_agent.Client)
    client.home = tmp_path
    client._process_started = 1_800_000_000.5
    client._irc_session_started = client._process_started
    client.request_shutdown = Mock()
    return client


@pytest.mark.parametrize("contents", ["1799983800 stop\n", "QUIT :restart\n", ""])
def test_stale_request_is_removed_without_shutdown(ear, contents):
    path = agent_control.quit_request_path(ear.home)
    path.write_text(contents, encoding="utf-8")
    old = ear._process_started - 4.5 * 3600
    os.utime(path, (old, old))

    assert not ear._consume_control_quit()
    assert not path.exists()
    ear.request_shutdown.assert_not_called()
    assert not ear._consume_control_quit()


@pytest.mark.parametrize("elapsed", [0.0, 0.1, 3600.0])
def test_live_request_still_shuts_down_after_reconnect(ear, elapsed):
    agent_control.request_agent_quit(ear.home, "restart")
    path = agent_control.quit_request_path(ear.home)
    written = ear._process_started + elapsed
    os.utime(path, (written, written))
    # A new IRC session is not a new process; requests during downtime stay valid.
    ear._irc_session_started = written + 10

    assert ear._consume_control_quit()
    assert not path.exists()
    ear.request_shutdown.assert_called_once_with(":control")
    assert not ear._consume_control_quit()


def test_missing_request_does_not_shutdown(ear):
    assert not ear._consume_control_quit()
    ear.request_shutdown.assert_not_called()


def test_consumer_without_cutoff_keeps_existing_contract(tmp_path):
    agent_control.request_agent_quit(tmp_path, "stop")
    assert agent_control.peek_quit_request(tmp_path) == "stop"
    assert agent_control.consume_quit_request(tmp_path) == "stop"
    assert agent_control.consume_quit_request(tmp_path) is None
