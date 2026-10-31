"""FR #5614: NETWORK/EXTENSION/LEGION usage; CTCP never reaches PowerShell."""
from __future__ import annotations

import airc_console as ac
import airc_extension as ex
import airc_legion as lg
import airc_network as nw
from airc_auth_helpers import ops_auth


def _core(**kw):
    auth = ops_auth("bob-marchhare", channel="#marchhare")
    return ac.AircConsoleCore(
        machine="marchhare", auth=auth, nick="marchhare_console", **kw
    )


def test_fr5614_network_bogus_is_usage_not_shell():
    parsed = nw.parse_network_command("id=458909c3 NETWORK bogus")
    assert parsed and parsed.get("usage")
    core = _core()
    hr = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :id=458909c3 NETWORK bogus"
    )
    assert hr is not None
    assert hr.action == "network"
    text = hr.reply or ""
    assert "code=usage" in text
    assert "NETWORK" in text
    assert "DONE id=458909c3 exit=2" in text
    assert "CommandNotFound" not in text


def test_fr5614_network_unknown_flag():
    parsed = nw.parse_network_command("id=58db83c3 NETWORK diag -Bogus")
    assert parsed and parsed.get("unknown_flag") == "-Bogus"
    core = _core()
    hr = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :id=58db83c3 NETWORK diag -Bogus"
    )
    assert "unknown-flag=-Bogus" in (hr.reply or "")
    assert "DONE id=58db83c3 exit=2" in (hr.reply or "")


def test_fr5614_extension_unknown_action():
    parsed = ex.parse_extension_command("id=86954147 EXTENSION frobnicate")
    assert parsed and parsed.get("usage")
    core = _core()
    hr = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :id=86954147 EXTENSION frobnicate"
    )
    assert hr.action == "extension"
    assert "code=usage" in (hr.reply or "")
    assert "DONE id=86954147 exit=2" in (hr.reply or "")
    assert "CommandNotFound" not in (hr.reply or "")


def test_fr5614_legion_force_is_unknown_flag():
    parsed = lg.parse_legion_command("id=1c0f7d9f LEGION flamingo -WhatIf -Force")
    assert parsed
    assert parsed.get("unknown_flag") == "-Force"
    core = _core()
    hr = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :id=1c0f7d9f LEGION flamingo -WhatIf -Force"
    )
    text = hr.reply or ""
    assert "unknown-flag=-Force" in text
    assert "reason=list" not in text
    assert "DONE id=1c0f7d9f exit=2" in text


def test_fr5614_ctcp_version_not_shell():
    core = _core()
    framed = "\x01VERSION\x01"
    hr = core.handle_raw(f":bob-marchhare!u@h PRIVMSG marchhare_console :{framed}")
    assert hr is not None
    assert hr.action.startswith("ctcp")
    assert "CommandNotFound" not in (hr.reply or "")


def test_fr5614_happy_network_diag_still_parses():
    p = nw.parse_network_command("id=aabbccdd NETWORK diag -WhatIf")
    assert p and not p.get("usage")
    assert p.get("whatif") is True
