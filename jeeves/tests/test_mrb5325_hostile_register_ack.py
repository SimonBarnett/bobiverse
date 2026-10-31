"""MRB #5325 hostile pins for FR #5274 ChanServ-before-ACK."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

IRC = ROOT / "common" / "scripts" / "irc_agent.py"
UC = ROOT / "common" / "scripts" / "unregister_cmd.py"
TEST = ROOT / "jeeves" / "tests" / "test_fr5274_register_chanserv_ack.py"


def test_mrb5325_pins_wait_then_ack():
    irc = IRC.read_text(encoding="utf-8")
    uc = UC.read_text(encoding="utf-8")
    t = TEST.read_text(encoding="utf-8")
    assert "FR #5274" in irc
    assert "_cs_register_wait" in irc
    assert "_expire_register_waits" in irc
    assert "ACK registered" in irc
    assert "REGISTERED v1" in uc or "REGISTERED_WIRE" in uc
    assert "BOB_CHANSERV_REGISTER_WAIT_S" in irc
    assert "test_fr5274_register_does_not_ack_before_chanserv" in t
    assert "test_fr5274_register_no_ack_on_timeout" in t
    assert "test_fr5274_register_ack_and_announce_on_chanserv_ok" in t
    # JOIN shop before REGISTER (ChanServ often requires presence)
    handle = irc[irc.find("def _handle_register_command") : irc.find("def _handle_unregister_command")]
    assert "JOIN {shop}" in handle
    assert "PRIVMSG ChanServ :REGISTER {shop}" in handle
    assert handle.find("JOIN {shop}") < handle.find("PRIVMSG ChanServ :REGISTER {shop}")
    # expire is invoked from the chair loop, not only tests
    assert "self._expire_register_waits()" in irc
    raw = IRC.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
