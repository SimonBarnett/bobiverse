"""FR #5742: ear must capture bad_id replies that echo a non-hex id= token."""
from __future__ import annotations

import irc_agent as ia


def test_fr5742_is_airc_console_reply_accepts_nonhex_bad_id():
    assert ia.is_airc_console_reply(
        "marchhare_console", "err id=zz5678nx seq=1 code=bad_id need-8-hex"
    )
    assert ia.is_airc_console_reply(
        "marchhare_console", "DONE id=zz5678nx exit=2"
    )
    assert ia.is_airc_console_reply(
        "marchhare_console", "DONE id=abc123 exit=2"
    )
    # Hex path unchanged.
    assert ia.is_airc_console_reply(
        "marchhare_console", "err id=abcdef12 seq=1 code=bad_id need-8-hex"
    )
    assert ia.is_airc_console_reply(
        "marchhare_console", "DONE id=abcdef12 exit=0"
    )
    # Still require *_console nick.
    assert not ia.is_airc_console_reply(
        "bob-marchhare", "err id=zz5678nx seq=1 code=bad_id need-8-hex"
    )
