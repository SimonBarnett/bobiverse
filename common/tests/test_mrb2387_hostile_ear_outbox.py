"""Hostile MRB #2387: FR #2384 ear outbox lint edges beyond implementer suite."""
from __future__ import annotations

from pathlib import Path

import irc_agent


def test_write_outbox_line_still_allows_ear_chat(tmp_path: Path):
    """Lint is drain-time only; intentional ear writes of non-job lines must still land."""
    path = tmp_path / "outbox.txt"
    irc_agent.write_outbox_line(path, "PRIVMSG #marchhare :ear status ok")
    text = path.read_text(encoding="utf-8")
    assert "PRIVMSG #marchhare :ear status ok" in text
    assert not text.startswith("\ufeff")


def test_giveup_reason_companion_line_is_not_job_wire():
    """Worker posts GIVEUP then a separate 'reason ...' line; only the verb line is refused."""
    assert irc_agent.is_misplaced_worker_job_wire(
        "PRIVMSG #marchhare :GIVEUP MRB SimonBarnett/bobiverse#2382"
    )
    assert not irc_agent.is_misplaced_worker_job_wire(
        "PRIVMSG #marchhare :reason self-MRB: this seat authored #2382"
    )


def test_ear_drain_skips_giveup_but_may_emit_reason(tmp_path, monkeypatch):
    out = tmp_path / "outbox.txt"
    out.write_text(
        "PRIVMSG #marchhare :GIVEUP MRB SimonBarnett/bobiverse#1\n"
        "PRIVMSG #marchhare :reason self-MRB\n",
        encoding="utf-8",
    )

    class FakeArgs:
        chair = False

    client = object.__new__(irc_agent.Client)
    client.args = FakeArgs()
    client.sock = object()
    client.chan = "#marchhare"
    client.original_nick = "Bob-marchhare"
    client.home = tmp_path
    sent: list[str] = []
    client.send_privmsg_lines = lambda line: sent.append(line) or [line]
    client.say = lambda line: None
    client.send = lambda *_a, **_k: None
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(irc_agent.bobreport, "chair_mode_active", lambda *_a, **_k: False)
    monkeypatch.setattr(irc_agent, "info", lambda *_a, **_k: None)

    got = client._drain_outbox_path(out)
    assert got == ["PRIVMSG #marchhare :reason self-MRB"]
    assert sent == got
