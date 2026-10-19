"""FR #4796: bob ear paces outbox PRIVMSG to *_console under Ergo flood limits.

Driver-side (ear drain) uses a longer sleep for console-targeted lines than the
default FLOOD_S so sequential Invoke-AircRemote Commands do not stack reply
bursts as tightly. Console token-bucket remains FR #4790.
"""
from __future__ import annotations

import irc_agent as agent


def test_fr4796_console_outbox_flood_slower_than_default():
    assert agent.CONSOLE_OUTBOX_FLOOD_S > agent.FLOOD_S
    assert agent.CONSOLE_OUTBOX_FLOOD_S >= 1.2


def test_fr4796_flood_s_for_outbox_line_console_vs_channel():
    console = "PRIVMSG rm-sql01_console :id=abcd1234 Get-Content x"
    shop = "PRIVMSG #flamingo :hello shop"
    bare = "hello bare"
    assert agent.flood_s_for_outbox_line(console) == agent.CONSOLE_OUTBOX_FLOOD_S
    assert agent.flood_s_for_outbox_line(shop) == agent.FLOOD_S
    assert agent.flood_s_for_outbox_line(bare) == agent.FLOOD_S


def test_fr4796_privmsg_target_helper():
    assert agent.privmsg_target("PRIVMSG marchhare_console :STATUS") == "marchhare_console"
    assert agent.privmsg_target("PRIVMSG #flamingo :x") == "#flamingo"
    assert agent.privmsg_target("not a privmsg") is None
