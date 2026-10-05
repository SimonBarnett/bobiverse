"""FR #2384: bob ear refuses worker ACK/DONE/NACK/GIVEUP job-wire lines in home\\outbox.txt."""
from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

import irc_agent


@pytest.mark.parametrize(
    "line,expect",
    [
        ("PRIVMSG #marchhare :ACK FR SimonBarnett/bobiverse#2384 implementing", True),
        ("PRIVMSG #marchhare :DONE FR SimonBarnett/bobiverse#2384 https://example.com/p/1", True),
        ("PRIVMSG #marchhare :DONE MRB SimonBarnett/bobiverse#9 PASS https://example.com/p/9", True),
        ("PRIVMSG #marchhare :NACK FR SimonBarnett/bobiverse#1", True),
        ("PRIVMSG #marchhare :GIVEUP UAT SimonBarnett/bobiverse#7 needs-ionos", True),
        ("ACK FR SimonBarnett/bobiverse#2384 bare form", True),
        ("DONE FR owner/repo#12 https://github.com/o/r/pull/1", True),
        ("PRIVMSG #marchhare :hello shop", False),
        ("PRIVMSG #bobiverse :status ok", False),
        ("reason self-MRB", False),
        ("!bored", False),
        ("", False),
    ],
)
def test_is_misplaced_worker_job_wire(line: str, expect: bool):
    assert irc_agent.is_misplaced_worker_job_wire(line) is expect


def _fake_ear_client(tmp_path: Path, *, chair: bool = False):
    class FakeArgs:
        pass

    args = FakeArgs()
    args.chair = chair
    client = object.__new__(irc_agent.Client)
    client.args = args
    client.sock = object()
    client.chan = "#marchhare"
    client.original_nick = "Bob-marchhare"
    client.home = tmp_path
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


def test_ear_drain_refuses_job_wire_but_sends_normal(tmp_path, monkeypatch):
    out = tmp_path / "outbox.txt"
    out.write_text(
        "\n".join(
            [
                "PRIVMSG #marchhare :ACK FR SimonBarnett/bobiverse#2384 oops",
                "PRIVMSG #marchhare :normal ear chat",
                "PRIVMSG #marchhare :DONE FR SimonBarnett/bobiverse#2384 https://example.com/p/1",
                "PRIVMSG #marchhare :still ok",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    client, sent, _said = _fake_ear_client(tmp_path, chair=False)
    warns: list[str] = []
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(irc_agent.bobreport, "chair_mode_active", lambda *_a, **_k: False)
    monkeypatch.setattr(irc_agent, "info", lambda msg: warns.append(str(msg)))

    got = client._drain_outbox_path(out)
    assert got == [
        "PRIVMSG #marchhare :normal ear chat",
        "PRIVMSG #marchhare :still ok",
    ]
    assert sent == got
    refused = [w for w in warns if "refused misplaced worker job-wire (FR #2384)" in w]
    assert len(refused) == 2
    # pos advanced past all four lines so they are not re-sent
    pos = int((tmp_path / "outbox.txt.pos").read_text(encoding="utf-8").strip())
    assert pos == out.stat().st_size
    again = client._drain_outbox_path(out)
    assert again == []


def test_chair_drain_still_sends_job_wire_lines(tmp_path, monkeypatch):
    """Chair home is not the worker mis-write target; do not refuse there."""
    out = tmp_path / "outbox.txt"
    out.write_text(
        "PRIVMSG #bobiverse :ACK FR SimonBarnett/bobiverse#1 title\n",
        encoding="utf-8",
    )
    client, sent, _said = _fake_ear_client(tmp_path, chair=True)
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(irc_agent.bobreport, "chair_mode_active", lambda *_a, **_k: False)

    got = client._drain_outbox_path(out)
    assert got == ["PRIVMSG #bobiverse :ACK FR SimonBarnett/bobiverse#1 title"]
    assert sent == got


def test_ear_drain_refuses_bare_ack_form(tmp_path, monkeypatch):
    out = tmp_path / "outbox.txt"
    out.write_text("ACK FR SimonBarnett/bobiverse#99 bare\nhello\n", encoding="utf-8")
    client, sent, said = _fake_ear_client(tmp_path, chair=False)
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(irc_agent.bobreport, "chair_mode_active", lambda *_a, **_k: False)
    monkeypatch.setattr(irc_agent, "info", lambda *_a, **_k: None)

    got = client._drain_outbox_path(out)
    # bare ACK refused; bare "hello" goes via say()
    assert "ACK FR SimonBarnett/bobiverse#99 bare" not in got
    assert sent == []
    assert said == ["hello"]
    assert got == ["hello"]
