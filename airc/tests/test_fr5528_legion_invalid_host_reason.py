"""FR #5528: LEGION bad_host! is reason=invalid, not reason=list."""
from __future__ import annotations

import airc_console as ac
import airc_legion as lg
from airc_auth_helpers import ops_auth


def test_fr5528_classify_invalid_vs_list():
    assert lg.parse_legion_command("LEGION flamingo,dodo")["error"] == "list"
    assert lg.parse_legion_command("LEGION bad_host!")["error"] == "invalid"
    assert lg.parse_legion_command("id=aabbccdd LEGION bad_host!")["error"] == "invalid"
    assert lg.parse_legion_command("LEGION walrus")["error"] is None


def test_fr5528_handle_raw_reason_invalid():
    auth = ops_auth("op", channel="#tm")
    core = ac.AircConsoleCore(machine="tm", auth=auth, nick="tm_console")
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=0bf5fb30 LEGION bad_host!")
    assert hr and hr.action == "capability_deny"
    assert "bad-target reason=invalid" in (hr.reply or "")
    assert "reason=list" not in (hr.reply or "")
