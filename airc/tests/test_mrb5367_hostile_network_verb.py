"""MRB #5367 hostile pins for NETWORK isolated worker (FR #5298)."""
from __future__ import annotations

import airc_console as ac
import airc_network as nw
from airc_auth_helpers import ops_auth
from repo_layout import ROOT


def _core(**kw):
    auth = ops_auth("op", channel="#tm")
    return ac.AircConsoleCore(machine="tm", auth=auth, nick="tm_console", **kw)


def test_mrb5367_shell_off_refuses():
    core = _core(capabilities=ac.ConsoleCapabilities(shell_mode="off"))
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :NETWORK diag")
    assert hr is not None
    assert hr.action == "capability_deny"
    assert hr.reply == "DONE exit=126 shell-disabled"


def test_mrb5367_stub_never_ldap():
    body = nw.stub_network_work("diag", whatif=False)
    assert body.get("ldap") is False
    assert body.get("hosts") == []


def test_mrb5367_whatif_still_stub():
    w = nw.parse_network_command("NETWORK -WhatIf")
    assert w is not None and w["whatif"] is True
    body = nw.stub_network_work(whatif=True)
    assert body["ldap"] is False
    assert body["whatif"] is True


def test_mrb5367_module_and_help_pin():
    src = (ROOT / "airc/scripts/airc_network.py").read_text(encoding="utf-8")
    cons = (ROOT / "airc/scripts/airc_console.py").read_text(encoding="utf-8")
    assert "workgroup-or-no-dc" in src
    assert '"ldap": False' in src or "ldap_ok" in src
    assert "airc-network-worker" in src
    assert "parse_network_command" in cons
    assert "update-disabled" in cons
    hr = _core().handle_raw(":op!u@h PRIVMSG tm_console :!help")
    assert "NETWORK" in (hr.reply or "")
    assert "password=" not in (hr.reply or "").lower()
