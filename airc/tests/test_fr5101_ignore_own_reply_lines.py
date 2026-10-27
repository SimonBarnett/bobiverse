"""FR #5101: console must not execute its own reply lines (Heard: loop)."""
from __future__ import annotations

import airc_console as ac


from airc_auth_helpers import ops_auth


def _core() -> ac.AircConsoleCore:
    auth = ops_auth("bob-marchhare", channel="#marchhare")
    return ac.AircConsoleCore(machine="marchhare", auth=auth, nick="marchhare_console")


def test_sanitize_heard_update_is_ignored_as_reply():
    heard = (
        "@marchhare_console marchhare here. weekly=1. "
        "Heard: UPDATE accepted status=scheduled product=airc version=1.0.4"
    )
    assert ac.sanitize_console_operator_text(heard).startswith("UPDATE accepted")
    assert ac.is_console_self_reply(ac.sanitize_console_operator_text(heard))


def test_handle_raw_does_not_shell_heard_update_or_done():
    core = _core()
    heard_u = (
        ":bob-marchhare!u@h PRIVMSG marchhare_console :"
        "@marchhare_console marchhare here. weekly=1. "
        "Heard: UPDATE accepted status=scheduled product=airc version=1.0.4"
    )
    hr = core.handle_raw(heard_u)
    assert hr is not None
    assert hr.action in {"empty", "ignore_reply"}
    assert hr.action != "update"
    heard_d = (
        ":bob-marchhare!u@h PRIVMSG marchhare_console :"
        "@marchhare_console marchhare here. weekly=1. "
        "Heard: DONE id=a00fb6d0 exit=0 bytes=19600 sha256=ab via=dcc"
    )
    hr2 = core.handle_raw(heard_d)
    assert hr2 is not None
    assert hr2.action in {"empty", "ignore_reply"}
    assert hr2.action not in {"shell", "job", "pipe"}
