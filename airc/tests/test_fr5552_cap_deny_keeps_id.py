"""FR #5552: LEGION/NETWORK/EXTENSION capability denies keep operator id=."""
from __future__ import annotations

import airc_console as ac
from airc_auth_helpers import ops_auth


def _core(**kw):
    auth = ops_auth("op", channel="#tm")
    return ac.AircConsoleCore(machine="tm", auth=auth, nick="tm_console", **kw)


def test_fr5552_legion_shell_off_keeps_id():
    core = _core(capabilities=ac.ConsoleCapabilities(shell_mode="off"))
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=aa11bb22 LEGION walrus")
    assert hr and hr.action == "capability_deny"
    assert hr.reply == "DONE id=aa11bb22 exit=126 shell-disabled"


def test_fr5552_legion_update_off_keeps_id():
    core = _core(capabilities=ac.ConsoleCapabilities(update="off"))
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=cc33dd44 LEGION walrus")
    assert hr and hr.action == "capability_deny"
    assert hr.reply == "DONE id=cc33dd44 exit=126 update-disabled"


def test_fr5552_network_update_off_keeps_id():
    core = _core(capabilities=ac.ConsoleCapabilities(update="off"))
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=11223344 NETWORK diag")
    assert hr and hr.action == "capability_deny"
    assert hr.reply == "DONE id=11223344 exit=126 update-disabled"


def test_fr5552_network_shell_off_keeps_id():
    core = _core(capabilities=ac.ConsoleCapabilities(shell_mode="off"))
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=55667788 NETWORK")
    assert hr and hr.action == "capability_deny"
    assert hr.reply == "DONE id=55667788 exit=126 shell-disabled"


def test_fr5552_extension_denies_keep_id():
    core = _core(capabilities=ac.ConsoleCapabilities(extension="off"))
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=99aabbcc EXTENSION install")
    assert hr and hr.action == "capability_deny"
    assert hr.reply == "DONE id=99aabbcc exit=126 extension-disabled"
    core2 = _core(capabilities=ac.ConsoleCapabilities(update="off", extension="on"))
    hr2 = core2.handle_raw(":op!u@h PRIVMSG tm_console :id=ddeeff00 EXTENSION status")
    assert hr2 and hr2.reply == "DONE id=ddeeff00 exit=126 update-disabled"
    core3 = _core(capabilities=ac.ConsoleCapabilities(shell_mode="off", extension="on"))
    hr3 = core3.handle_raw(":op!u@h PRIVMSG tm_console :id=01020304 EXTENSION status")
    assert hr3 and hr3.reply == "DONE id=01020304 exit=126 shell-disabled"


def test_fr5552_no_id_still_bare_done():
    core = _core(capabilities=ac.ConsoleCapabilities(update="off"))
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :LEGION walrus")
    assert hr and hr.reply == "DONE exit=126 update-disabled"
