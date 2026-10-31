"""FR #5539: never split long outbox PRIVMSG to *_console into executable fragments."""
from __future__ import annotations

import irc_agent as agent


def test_fr5539_long_console_privmsg_is_rejected_not_split():
    body = "id=aabbccdd cmd: " + ("schtasks /create /tn x /tr y " * 20)
    line = f"PRIVMSG marchhare_console :{body}"
    assert len(body) > 400
    out = agent.expand_irc_outbound_line(line, nick="Bob-marchhare", text_max=80)
    assert out == []


def test_fr5539_short_console_privmsg_still_sent_once():
    line = "PRIVMSG marchhare_console :id=aabbccdd STATUS"
    out = agent.expand_irc_outbound_line(line, nick="Bob-marchhare", text_max=80)
    assert out == [line]


def test_fr5539_channel_privmsg_still_splits():
    body = "hello " * 40
    line = f"PRIVMSG #flamingo :{body}"
    out = agent.expand_irc_outbound_line(line, nick="Bob-flamingo", text_max=40)
    assert len(out) > 1
    assert all(w.startswith("PRIVMSG #flamingo :") for w in out)
