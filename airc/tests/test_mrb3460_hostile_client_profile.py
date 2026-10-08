"""Hostile pins for MRB #3460 / FR #3401 AIRC_PROFILE=client."""
from __future__ import annotations

from pathlib import Path

import airc_console as ac
from repo_layout import ROOT

INSTALL = ROOT / "airc/scripts/Install-Airc.ps1"
SERVICE = ROOT / "airc/scripts/airc_console_service.py"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"
POST = ROOT / "common/docs/post-install.md"


def test_mrb3460_auth_irc_ops_contiguous_and_fleet_silent():
    m = ac.ChannelMemberMap(channel="#box")
    m.apply_names("@op %hop plain")
    m.mark_synced()
    auth = ac.AuthPolicy(
        auth_mode="irc_ops",
        members=m,
        self_nicks={"box_console"},
        machine="box",
    )
    assert auth.allow("op") and auth.allow("hop") and not auth.allow("plain")
    assert not auth.allow("box_console")
    core = ac.AircConsoleCore(
        machine="box", auth=auth, nick="box_console"
    )
    core.channel = "#box"
    deny = core.handle_raw(":plain!u@h PRIVMSG box_console :STATUS")
    assert deny is not None and deny.action == "deny"
    assert deny.reply == "DONE exit=126 not-op"
    fleet = ac.AircConsoleCore(
        machine="box",
        auth=ac.AuthPolicy(operators={"op"}, machine="box"),
        nick="box_console",
    )
    fleet.channel = "#box"
    silent = fleet.handle_raw(":op!u@h PRIVMSG #box :STATUS")
    assert silent is not None and silent.action == "silent_channel"


def test_mrb3460_install_client_caps_and_auth_mode_wiring():
    t = INSTALL.read_text(encoding="utf-8-sig")
    assert "prof -in @('workstation', 'client')" in t or "prof -eq 'client'" in t
    assert "elseif ($prof -eq 'client') { $resolvedShell = 'operators' }" in t
    assert "elseif ($prof -eq 'client') { $resolvedJobs = 'on' }" in t
    assert "elseif ($prof -in @('workstation', 'client')) { $resolvedSelf = $false }" in t
    assert "authMode = $(if ($prof -eq 'client') { 'irc_ops' } else { 'operators' })" in t
    assert "client keeps crash reports ON" in t or "source = 'client-profile'" in t
    assert "no operators.txt (IRC +o/+h auth)" in t


def test_mrb3460_service_control_channel_log_and_names_wiring():
    t = SERVICE.read_text(encoding="utf-8")
    assert "control_channel_log_line" in t
    assert 'info(control_channel_log_line(self.channel, "registered"))' in t
    assert 'info(control_channel_log_line(self.channel, "domain-lobby"))' in t
    assert "ChannelMemberMap" in t
    assert 'choices=["operators", "irc_ops"]' in t or '"irc_ops"' in t


def test_mrb3460_docs_skill_single_property_command():
    assert "AIRC_PROFILE=client" in POST.read_text(encoding="utf-8")
    assert "AIRC_PROFILE=client" in SKILL.read_text(encoding="utf-8")
    assert "irc_ops" in SKILL.read_text(encoding="utf-8")
    assert ac.control_channel_reason("registered") == "registered-machine"
    assert ac.control_channel_reason("domain-lobby") == "domain-fallback"
