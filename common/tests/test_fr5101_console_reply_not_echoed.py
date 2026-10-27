"""FR #5101: bob must not mention-ack airc console reply PMs (Heard: loop)."""
from __future__ import annotations

import bobtalk
import irc_agent as ia


def test_is_airc_console_reply_covers_update_accepted_and_dcc_done():
    assert ia.is_airc_console_reply(
        "marchhare_console",
        "UPDATE accepted status=scheduled product=airc version=1.0.4",
    )
    assert ia.is_airc_console_reply(
        "marchhare_console",
        "DONE id=a00fb6d0 exit=0 bytes=19600 sha256=abc via=dcc",
    )
    assert ia.is_airc_console_reply(
        "marchhare_console",
        "out id=a00fb6d0 seq=1 bulk bytes=19600 sha256=abc (FR #5003 DCC)",
    )
    assert not ia.is_airc_console_reply("bob-marchhare", "UPDATE accepted status=scheduled")
    assert not ia.is_airc_console_reply("marchhare_console", "cmd: echo hi")


def test_should_not_mention_ack_console_nicks():
    assert bobtalk.should_answer_asker("simon") is True
    assert bobtalk.should_answer_asker("marchhare_console") is False
    assert (
        bobtalk.mention_reply_line(
            __import__("pathlib").Path("."),
            "marchhare",
            ["bob-marchhare"],
            "marchhare_console",
            "UPDATE accepted status=scheduled product=airc",
            to_me=True,
        )
        is None
    )
