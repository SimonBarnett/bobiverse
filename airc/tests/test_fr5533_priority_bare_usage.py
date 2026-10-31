"""FR #5533: bare PRIORITY is usage, not PowerShell."""
from __future__ import annotations

import airc_console as ac
import airc_priority as ap
from airc_auth_helpers import ops_auth


def _core(**kw):
    auth = ops_auth("bob-marchhare", channel="#marchhare")
    return ac.AircConsoleCore(
        machine="marchhare", auth=auth, nick="marchhare_console", **kw
    )


def test_fr5533_parse_usage_bare_and_unknown():
    assert ap.parse_priority_usage("PRIORITY") is not None
    assert ap.parse_priority_usage("id=aabbccdd PRIORITY") == "aabbccdd"
    assert ap.parse_priority_usage("id=aabbccdd PRIORITY   ") == "aabbccdd"
    assert ap.parse_priority_usage("PRIORITY nope") == ""
    assert ap.parse_priority_usage("PRIORITY connect dev1") is None
    assert ap.parse_priority_usage("PRIORITY status") is None
    assert ap.parse_priority_usage("PRIORITY prepare FOO") is None
    assert ap.parse_priority_usage("PRIORITY formStart instance=x") is None
    assert ap.parse_priority_command("PRIORITY") is None


def test_fr5533_handle_bare_usage_not_shell():
    core = _core()
    hr = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :id=aabbccdd PRIORITY"
    )
    assert hr is not None
    assert hr.action == "priority"
    text = hr.reply or ""
    assert "code=usage" in text
    assert "err id=aabbccdd" in text
    assert "DONE id=aabbccdd exit=2" in text
    assert "connect" in text and "status" in text
    assert "CommandNotFound" not in text


def test_fr5533_unknown_subverb_usage():
    core = _core()
    hr = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :id=11223344 PRIORITY frob"
    )
    assert hr and hr.action == "priority"
    assert "DONE id=11223344 exit=2" in (hr.reply or "")
    assert "code=usage" in (hr.reply or "")


def test_fr5533_prepare_still_not_usage():
    assert ap.parse_priority_usage("id=aabbccdd PRIORITY prepare FOO") is None
