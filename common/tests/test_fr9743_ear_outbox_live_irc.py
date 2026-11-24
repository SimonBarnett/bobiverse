"""FR #9743: disconnected / duplicate bob-ear must not advance outbox.pos.

Acceptance:
- Outbox consumer owns live IRC before advancing pos
- Disconnected ear must not move pos
- Single-instance lock per home/nick
"""
from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

import irc_agent


def _fake_ear_client(tmp_path: Path, *, chair: bool = False):
    class FakeArgs:
        pass

    args = FakeArgs()
    args.chair = chair
    client = object.__new__(irc_agent.Client)
    client.args = args
    client.sock = object()
    client.chan = "#flamingo"
    client.original_nick = "Bob-flamingo"
    client.home = tmp_path
    client.joined = __import__("threading").Event()
    client.joined.set()
    client.dead = __import__("threading").Event()
    client.stop = __import__("threading").Event()
    client._cred_seal_sweep_pending = False
    sent_wire: list[str] = []
    said: list[str] = []

    def fake_send_privmsg_lines(line):
        sent_wire.append(line)
        return [line]

    def fake_say(line):
        said.append(line)

    client.send_privmsg_lines = fake_send_privmsg_lines  # type: ignore[method-assign]
    client.say = fake_say  # type: ignore[method-assign]
    client.send = lambda *_a, **_k: None  # type: ignore[method-assign]
    return client, sent_wire, said


def test_fr9743_sock_none_does_not_move_pos(tmp_path, monkeypatch):
    out = tmp_path / "outbox.txt"
    out.write_text("PRIVMSG #flamingo :!assign\n", encoding="utf-8")
    client, sent, _said = _fake_ear_client(tmp_path)
    client.sock = None
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(irc_agent.bobreport, "chair_mode_active", lambda *_a, **_k: False)

    got = client._drain_outbox_path(out)
    assert got == []
    assert sent == []
    assert not (tmp_path / "outbox.txt.pos").exists()


def test_fr9743_dead_does_not_move_pos(tmp_path, monkeypatch):
    out = tmp_path / "outbox.txt"
    out.write_text("PRIVMSG #flamingo :!assign\n", encoding="utf-8")
    client, sent, _said = _fake_ear_client(tmp_path)
    client.dead.set()
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(irc_agent.bobreport, "chair_mode_active", lambda *_a, **_k: False)

    got = client._drain_outbox_path(out)
    assert got == []
    assert sent == []
    assert not (tmp_path / "outbox.txt.pos").exists()


def test_fr9743_not_joined_does_not_move_pos(tmp_path, monkeypatch):
    out = tmp_path / "outbox.txt"
    out.write_text("PRIVMSG #flamingo :!assign\n", encoding="utf-8")
    client, sent, _said = _fake_ear_client(tmp_path)
    client.joined.clear()
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(irc_agent.bobreport, "chair_mode_active", lambda *_a, **_k: False)

    got = client._drain_outbox_path(out)
    assert got == []
    assert sent == []
    assert not (tmp_path / "outbox.txt.pos").exists()


def test_fr9743_send_oserror_does_not_advance_past_failed_line(tmp_path, monkeypatch):
    out = tmp_path / "outbox.txt"
    lines = [
        "PRIVMSG #flamingo :first ok",
        "PRIVMSG #flamingo :!assign boom",
        "PRIVMSG #flamingo :after fail",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    client, sent, _said = _fake_ear_client(tmp_path)
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(irc_agent.bobreport, "chair_mode_active", lambda *_a, **_k: False)
    monkeypatch.setattr(irc_agent, "info", lambda *_a, **_k: None)

    def flaky_send(line):
        if "!assign" in line:
            raise OSError(10054, "connection reset")
        sent.append(line)
        return [line]

    client.send_privmsg_lines = flaky_send  # type: ignore[method-assign]

    got = client._drain_outbox_path(out)
    assert got == ["PRIVMSG #flamingo :first ok"]
    assert sent == ["PRIVMSG #flamingo :first ok"]
    pos = int((tmp_path / "outbox.txt.pos").read_text(encoding="utf-8").strip())
    # Stopped before the failed line; pos must leave !assign for a live ear.
    records, _ = irc_agent.take_outbox_records(out, 0, max_lines=1)
    assert records, "expected first outbox record"
    first_end = records[0][2]
    assert pos == first_end
    # Failed line must still be unread.
    remaining, _ = irc_agent.take_outbox_records(out, pos, max_lines=10)
    assert remaining[0][0] == "PRIVMSG #flamingo :!assign boom"
    again = client._drain_outbox_path(out)
    # Still fails on the same line; pos unchanged.
    assert again == []
    assert int((tmp_path / "outbox.txt.pos").read_text(encoding="utf-8").strip()) == first_end


def test_fr9743_live_drain_still_advances_on_success(tmp_path, monkeypatch):
    out = tmp_path / "outbox.txt"
    out.write_text("PRIVMSG #flamingo :hello\n", encoding="utf-8")
    client, sent, _said = _fake_ear_client(tmp_path)
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(irc_agent.bobreport, "chair_mode_active", lambda *_a, **_k: False)
    monkeypatch.setattr(irc_agent, "info", lambda *_a, **_k: None)

    got = client._drain_outbox_path(out)
    assert got == ["PRIVMSG #flamingo :hello"]
    assert sent == got
    pos = int((tmp_path / "outbox.txt.pos").read_text(encoding="utf-8").strip())
    assert pos == out.stat().st_size


def test_fr9743_ear_instance_lock_blocks_second(tmp_path):
    nick = "Bob-flamingo"
    held = irc_agent.acquire_ear_instance_lock(tmp_path, nick)
    assert held is not None
    try:
        second = irc_agent.acquire_ear_instance_lock(tmp_path, nick)
        assert second is None
    finally:
        irc_agent.release_ear_instance_lock(held)


def test_fr9743_ear_instance_lock_distinct_nicks(tmp_path):
    a = irc_agent.acquire_ear_instance_lock(tmp_path, "Bob-a")
    b = irc_agent.acquire_ear_instance_lock(tmp_path, "Bob-b")
    assert a is not None and b is not None
    irc_agent.release_ear_instance_lock(a)
    irc_agent.release_ear_instance_lock(b)


def test_fr9743_irc_live_for_outbox_helper(tmp_path):
    client, _sent, _said = _fake_ear_client(tmp_path)
    assert client.irc_live_for_outbox() is True
    client.sock = None
    assert client.irc_live_for_outbox() is False
    client.sock = object()
    client.dead.set()
    assert client.irc_live_for_outbox() is False
