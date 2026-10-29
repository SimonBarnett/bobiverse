"""FR #5196: a previous process's quit request must not stop a restarted ear."""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
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


def test_request_during_startup_before_client_construction_is_live(tmp_path, monkeypatch):
    started = 1_800_000_000.5
    monkeypatch.setattr(irc_agent, "_PROCESS_STARTED", started)
    monkeypatch.setattr(irc_agent.time, "time", lambda: started + 30)
    monkeypatch.setattr(irc_agent.bob_home, "ensure_homes", lambda **kwargs: None)
    monkeypatch.delenv("BOB_IRC_DEBUG", raising=False)
    monkeypatch.setenv("BOB_HOME", str(tmp_path))
    agent_control.request_agent_quit(tmp_path, "stop")
    path = agent_control.quit_request_path(tmp_path)
    os.utime(path, (started + 10, started + 10))
    client = irc_agent.Client(SimpleNamespace(
        nick="Bob-test", channel="#test", home=str(tmp_path), outbox=None,
    ))
    client.request_shutdown = Mock()

    assert client._process_started == started
    assert client._consume_control_quit()
    client.request_shutdown.assert_called_once_with(":control")
    assert not path.exists()


def test_install_and_upgrade_set_appdirectory_after_service_registration():
    installer = Path(__file__).resolve().parents[1] / "scripts" / "Install-Bob.ps1"
    text = installer.read_text(encoding="utf-8-sig")
    remove = text.index("Remove-BobiverseService -Nssm $Nssm -Name $ServiceName")
    install = text.index(
        "[void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('install',"
    )
    directory = (
        "[void](Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs "
        "@('set', $ServiceName, 'AppDirectory', (Join-Path $InstallRoot 'scripts')))"
    )
    # Upgrade removes/re-registers the service; the same unconditional settings
    # must run for clean installs and upgrades, before the service starts.
    registration = text[install:text.index(directory)]
    assert remove < install < text.index(directory) < text.index("Start-Service $ServiceName")
    assert all(
        line.startswith("[void](Invoke-BobiverseNssmChecked ")
        for line in registration.splitlines()
    )
