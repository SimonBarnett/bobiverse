"""FR #5527: LEGION bad-target DONE must carry id= so the ear can correlate."""
from __future__ import annotations

import airc_console as ac
from airc_auth_helpers import ops_auth


def _core(**kw):
    auth = ops_auth("op", channel="#tm")
    return ac.AircConsoleCore(machine="tm", auth=auth, nick="tm_console", **kw)


def test_fr5527_empty_target_keeps_id():
    hr = _core().handle_raw(":op!u@h PRIVMSG tm_console :id=9c78bf44 LEGION")
    assert hr and hr.action == "capability_deny"
    assert hr.reply == "DONE id=9c78bf44 exit=126 bad-target reason=empty"


def test_fr5527_list_target_keeps_id():
    hr = _core().handle_raw(":op!u@h PRIVMSG tm_console :id=815f427b LEGION flamingo,dodo")
    assert hr and hr.action == "capability_deny"
    assert "DONE id=815f427b exit=126 bad-target reason=list" == hr.reply


def test_fr5527_invalid_host_keeps_id():
    hr = _core().handle_raw(":op!u@h PRIVMSG tm_console :id=0bf5fb30 LEGION bad_host!")
    assert hr and hr.action == "capability_deny"
    assert hr.reply.startswith("DONE id=0bf5fb30 exit=126 bad-target reason=")
    assert "id=0bf5fb30" in (hr.reply or "")


def test_fr5527_no_id_still_done_without_inventing():
    hr = _core().handle_raw(":op!u@h PRIVMSG tm_console :LEGION a,b")
    assert hr and hr.action == "capability_deny"
    assert "DONE exit=126 bad-target" in (hr.reply or "")
    assert "id=" not in (hr.reply or "")
