"""FR #9743: disconnected bob-ear must not advance outbox.pos; live IRC gate + single-instance lock."""
from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest

import irc_agent


class FakeArgs:
    """Minimal args for Client construction."""

    def __init__(self, **kwargs):
        self.chair = kwargs.get("chair", False)
        self.nick = kwargs.get("nick", "Bob-test")
        self.channel = kwargs.get("channel", "#test")
        self.home = kwargs.get("home", None)
        self.outbox = kwargs.get("outbox", None)
        self.host = "irc.test"
        self.port = 6697
        self.password = ""
        self.realname = "test"
        self.hello = ""
        self.announce_key = False
        self.once = False
        self.auto_nick = False
        self.install_root = ""


def _fake_ear_client(tmp_path: Path, *, sock=True, joined=False, dead=False, stop=False):
    """Create a minimal fake Client for outbox testing."""
    args = FakeArgs(home=str(tmp_path))
    client = object.__new__(irc_agent.Client)
    client.args = args
    client.sock = object() if sock else None
    client.chan = "#test"
    client.original_nick = "Bob-test"
    client.home = tmp_path
    client.joined = mock.Mock()
    client.joined.is_set.return_value = joined
    client.dead = mock.Mock()
    client.dead.is_set.return_value = dead
    client.stop = mock.Mock()
    client.stop.is_set.return_value = stop
    client._cred_seal_sweep_pending = False
    
    sent_wire: list[str] = []
    said: list[str] = []

    def fake_send_privmsg_lines(line):
        sent_wire.append(line)
        return [line]

    def fake_say(line):
        said.append(line)

    client.send_privmsg_lines = fake_send_privmsg_lines
    client.say = fake_say
    client.send = lambda *_a, **_k: None
    client._maybe_local_outbox_startworker = lambda *_a, **_k: None
    
    return client, sent_wire, said


def test_irc_live_for_outbox_all_conditions():
    """Test irc_live_for_outbox() checks all conditions."""
    args = FakeArgs()
    client = object.__new__(irc_agent.Client)
    client.args = args
    client.sock = None
    client.joined = mock.Mock()
    client.joined.is_set.return_value = True
    client.dead = mock.Mock()
    client.dead.is_set.return_value = False
    client.stop = mock.Mock()
    client.stop.is_set.return_value = False
    
    # No socket -> not live
    assert not client.irc_live_for_outbox()
    
    # Has socket but not joined
    client.sock = object()
    client.joined.is_set.return_value = False
    assert not client.irc_live_for_outbox()
    
    # Joined but dead
    client.joined.is_set.return_value = True
    client.dead.is_set.return_value = True
    assert not client.irc_live_for_outbox()
    
    # Joined but stop requested
    client.dead.is_set.return_value = False
    client.stop.is_set.return_value = True
    assert not client.irc_live_for_outbox()
    
    # All conditions met
    client.stop.is_set.return_value = False
    assert client.irc_live_for_outbox()


def test_disconnected_ear_does_not_advance_pos(tmp_path, monkeypatch):
    """Disconnected ear (no socket) must not read or advance outbox.pos (FR #9743)."""
    out = tmp_path / "outbox.txt"
    out.write_text("PRIVMSG #test :hello\n", encoding="utf-8")
    
    client, _sent, _said = _fake_ear_client(tmp_path, sock=False, joined=False)
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(irc_agent.bobreport, "chair_mode_active", lambda *_a, **_k: False)
    
    got = client._drain_outbox_path(out)
    assert got == []  # Nothing sent
    
    # Verify pos file was not created (ear never read the outbox)
    pos_file = tmp_path / "outbox.txt.pos"
    assert not pos_file.exists()


def test_not_joined_ear_does_not_advance_pos(tmp_path, monkeypatch):
    """Ear with socket but not yet joined must not read outbox.pos (FR #9743)."""
    out = tmp_path / "outbox.txt"
    out.write_text("PRIVMSG #test :hello\n", encoding="utf-8")
    
    client, _sent, _said = _fake_ear_client(tmp_path, sock=True, joined=False, dead=False)
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(irc_agent.bobreport, "chair_mode_active", lambda *_a, **_k: False)
    
    got = client._drain_outbox_path(out)
    assert got == []  # Nothing sent
    
    # Verify pos file was not created
    pos_file = tmp_path / "outbox.txt.pos"
    assert not pos_file.exists()


def test_dead_ear_does_not_advance_pos(tmp_path, monkeypatch):
    """Dead ear must not read or advance outbox.pos even if joined (FR #9743)."""
    out = tmp_path / "outbox.txt"
    out.write_text("PRIVMSG #test :hello\n", encoding="utf-8")
    
    client, _sent, _said = _fake_ear_client(tmp_path, sock=True, joined=True, dead=True)
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(irc_agent.bobreport, "chair_mode_active", lambda *_a, **_k: False)
    
    got = client._drain_outbox_path(out)
    assert got == []  # Nothing sent
    
    # Verify pos file was not created
    pos_file = tmp_path / "outbox.txt.pos"
    assert not pos_file.exists()


def test_stop_ear_does_not_advance_pos(tmp_path, monkeypatch):
    """Stopping ear must not advance outbox.pos (FR #9743)."""
    out = tmp_path / "outbox.txt"
    out.write_text("PRIVMSG #test :hello\n", encoding="utf-8")
    
    client, _sent, _said = _fake_ear_client(tmp_path, sock=True, joined=True, stop=True)
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(irc_agent.bobreport, "chair_mode_active", lambda *_a, **_k: False)
    
    got = client._drain_outbox_path(out)
    assert got == []  # Nothing sent
    
    # Verify pos file was not created
    pos_file = tmp_path / "outbox.txt.pos"
    assert not pos_file.exists()


def test_live_ear_drains_and_advances_pos(tmp_path, monkeypatch):
    """Live ear (socket + joined + not dead/stop) can read and advance outbox.pos (FR #9743)."""
    out = tmp_path / "outbox.txt"
    out.write_text("PRIVMSG #test :hello\n", encoding="utf-8")
    
    client, sent, _said = _fake_ear_client(tmp_path, sock=True, joined=True, dead=False)
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(irc_agent.bobreport, "chair_mode_active", lambda *_a, **_k: False)
    
    got = client._drain_outbox_path(out)
    assert got == ["PRIVMSG #test :hello"]  # Line was sent
    assert sent == ["PRIVMSG #test :hello"]
    
    # Verify pos file was created and advanced
    pos_file = tmp_path / "outbox.txt.pos"
    assert pos_file.exists()
    pos = int(pos_file.read_text(encoding="utf-8").strip())
    assert pos == out.stat().st_size  # pos advanced to EOF


def test_send_error_does_not_advance_pos(tmp_path, monkeypatch):
    """OSError during send must not advance outbox.pos (FR #9743 commit-on-success)."""
    out = tmp_path / "outbox.txt"
    out.write_text("PRIVMSG #test :hello\n", encoding="utf-8")
    
    client, _sent, _said = _fake_ear_client(tmp_path, sock=True, joined=True, dead=False)
    
    # Mock send to raise OSError
    client.send_privmsg_lines = lambda *_a, **_k: (_ for _ in ()).throw(
        OSError("send failed")
    )
    
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(irc_agent.bobreport, "chair_mode_active", lambda *_a, **_k: False)
    
    got = client._drain_outbox_path(out)
    assert got == []  # Nothing sent; line was not consumed
    
    # Verify pos file was not created
    pos_file = tmp_path / "outbox.txt.pos"
    assert not pos_file.exists()


def test_ear_lock_path():
    """Test ear_lock_path generates correct lock file path."""
    home = Path("/home/test")
    nick = "Bob-test"
    lock = irc_agent.ear_lock_path(home, nick)
    assert lock == Path("/home/test/ear.Bob-test.lock")


def test_process_alive_check():
    """Test _process_alive checks process existence."""
    # Current process should be alive
    assert irc_agent._process_alive(os.getpid()) is True
    
    # Non-existent PID should not be alive
    # Use a very high PID that shouldn't exist
    assert irc_agent._process_alive(999999999) is False


def test_acquire_ear_lock_no_prior(tmp_path, monkeypatch):
    """Test acquiring lock when no prior lock exists."""
    home = tmp_path
    nick = "Bob-test"
    
    result = irc_agent.acquire_ear_lock(home, nick)
    assert result is True
    
    lock_file = irc_agent.ear_lock_path(home, nick)
    assert lock_file.exists()
    pid_in_lock = int(lock_file.read_text(encoding="utf-8").strip())
    assert pid_in_lock == os.getpid()


def test_acquire_ear_lock_dead_prior(tmp_path, monkeypatch):
    """Test acquiring lock when a dead prior held it."""
    home = tmp_path
    nick = "Bob-test"
    lock_file = irc_agent.ear_lock_path(home, nick)
    
    # Write a dead PID to the lock file
    dead_pid = 999999999
    lock_file.write_text(str(dead_pid) + "\n", encoding="utf-8")
    
    # Should succeed because the prior is dead
    result = irc_agent.acquire_ear_lock(home, nick)
    assert result is True
    
    # Lock should now contain our PID
    pid_in_lock = int(lock_file.read_text(encoding="utf-8").strip())
    assert pid_in_lock == os.getpid()


def test_acquire_ear_lock_duplicate_live(tmp_path, monkeypatch):
    """Test that duplicate live ear exits with code 3 (FR #9743)."""
    home = tmp_path
    nick = "Bob-test"
    lock_file = irc_agent.ear_lock_path(home, nick)
    
    # Write current PID to lock (simulating a live prior)
    lock_file.write_text(str(os.getpid()) + "\n", encoding="utf-8")
    
    # Trying to acquire should exit with code 3
    with pytest.raises(SystemExit) as exc_info:
        irc_agent.acquire_ear_lock(home, nick)
    
    assert exc_info.value.code == 3


def test_release_ear_lock(tmp_path):
    """Test releasing lock file."""
    home = tmp_path
    nick = "Bob-test"
    lock_file = irc_agent.ear_lock_path(home, nick)
    
    # Create lock
    irc_agent.acquire_ear_lock(home, nick)
    assert lock_file.exists()
    
    # Release lock
    irc_agent.release_ear_lock(home, nick)
    assert not lock_file.exists()


def test_release_ear_lock_already_gone(tmp_path):
    """Test releasing lock when file doesn't exist (should not raise)."""
    home = tmp_path
    nick = "Bob-test"
    
    # Should not raise when lock doesn't exist
    irc_agent.release_ear_lock(home, nick)
