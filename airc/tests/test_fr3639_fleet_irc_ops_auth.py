"""FR #3639: every airc profile authorises by live control-channel +o/+h only.

No operators.txt, no fleet-operators.txt roster and no nick allow-list on fleet,
workstation or client. Fleet (and workstation) still take commands by DM only and
stay silent in channel; the client profile also accepts commands in the control
channel. The *who* check is the same live channel-status check either way.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import airc_console as ac
import airc_console_service as svc
from repo_layout import ROOT

COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
INSTALL = ROOT / "airc/scripts/Install-Airc.ps1"
INSTALL_CONSOLE = ROOT / "airc/scripts/Install-AircConsole.ps1"
PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"
UPDATE = ROOT / "common/scripts/Update-BobiverseService.ps1"
START = ROOT / "airc/scripts/Start-AircConsole.ps1"


def _members(*names: str, channel: str = "#marchhare") -> ac.ChannelMemberMap:
    m = ac.ChannelMemberMap(channel=channel)
    m.apply_names(" ".join(names))
    m.mark_synced()
    return m


class _StubJobs:
    """Job protocol stub so granted commands route to ``job`` without running a shell."""

    def handle_async(self, nick, verb, kv):  # noqa: ANN001
        self.last = (nick, verb, kv)


def _fleet_core(members: ac.ChannelMemberMap, nick: str = "marchhare_console") -> ac.AircConsoleCore:
    """Fleet install: channel-status auth, commands by DM only (no operators file)."""
    auth = ac.AuthPolicy(members=members, self_nicks={nick})
    core = ac.AircConsoleCore(machine="marchhare", auth=auth, nick=nick, job_protocol=_StubJobs())
    core.channel = members.channel
    return core


def test_fleet_grants_ops_and_halfops_denies_plain_with_no_operators_file(tmp_path: Path):
    assert not (tmp_path / "operators.txt").exists()
    assert not (tmp_path / "fleet-operators.txt").exists()
    m = _members("@simon", "%bob-other", "+voiced", "plain")
    core = _fleet_core(m)

    op = core.handle_raw(":simon!u@h PRIVMSG marchhare_console :STATUS")
    assert op is not None and op.action == "job"
    hop = core.handle_raw(":bob-other!u@h PRIVMSG marchhare_console :STATUS")
    assert hop is not None and hop.action == "job"

    for nick in ("plain", "voiced", "stranger"):
        hr = core.handle_raw(f":{nick}!u@h PRIVMSG marchhare_console :STATUS")
        assert hr is not None and hr.action == "deny", nick
        assert hr.reply == "DONE exit=126 not-op"
        assert hr.deny_reason == "not-op"

    # Fleet stays silent in channel even for an op (chair / git-claim traffic lives there).
    ch = core.handle_raw(":simon!u@h PRIVMSG #marchhare :STATUS")
    assert ch is not None and ch.action == "silent_channel"


def test_fleet_refuses_until_names_synced_and_refuses_self_nick():
    m = ac.ChannelMemberMap(channel="#marchhare")
    m.apply_names("@simon")
    core = _fleet_core(m)
    hr = core.handle_raw(":simon!u@h PRIVMSG marchhare_console :STATUS")
    assert hr is not None and hr.action == "deny"
    assert hr.deny_reason == "channel-state-unknown"
    m.mark_synced()
    hr = core.handle_raw(":marchhare_console!u@h PRIVMSG marchhare_console :STATUS")
    assert hr is not None and hr.action == "deny"
    assert hr.deny_reason == "self-nick"


def test_deop_and_reop_take_effect_live():
    m = _members("@simon")
    core = _fleet_core(m)
    assert core.auth.allow("simon")
    m.on_mode("#marchhare", "-o", ["simon"])
    assert not core.auth.allow("simon")
    m.on_mode("#marchhare", "+h", ["simon"])
    assert core.auth.allow("simon")
    # Voice never grants control.
    m.on_mode("#marchhare", "-h+v", ["simon", "simon"])
    assert not core.auth.allow("simon")


def test_client_profile_reads_commands_from_the_control_channel():
    assert ac.resolve_channel_commands({"profile": "client"}) is True
    assert ac.resolve_channel_commands({"profile": "fleet"}) is False
    assert ac.resolve_channel_commands({"profile": "workstation"}) is False
    assert ac.resolve_channel_commands({}) is False
    m = _members("@simon", "plain", channel="#acme")
    auth = ac.AuthPolicy(members=m, self_nicks={"acme_console"})
    core = ac.AircConsoleCore(
        machine="acme", auth=auth, nick="acme_console", channel_commands=True, job_protocol=_StubJobs()
    )
    core.channel = "#acme"
    ok = core.handle_raw(":simon!u@h PRIVMSG #acme :STATUS")
    assert ok is not None and ok.action == "job"
    deny = core.handle_raw(":plain!u@h PRIVMSG #acme :STATUS")
    assert deny is not None and deny.action == "deny"


def test_service_ignores_operators_file_and_cli_list(tmp_path: Path, monkeypatch):
    """An operators.txt present in the console home must never authorise anyone."""
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "x-server-pass")
    (tmp_path / "operators.txt").write_text("stranger\n", encoding="utf-8")
    args = svc.build_arg_parser().parse_args(
        ["--machine", "marchhare", "--home", str(tmp_path), "--shop-mode", "registered",
         "--operators", "stranger", "--operators-file", str(tmp_path / "operators.txt"),
         "--auth-mode", "operators", "--require-account", "--accounts", "stranger"]
    )
    s = svc.AircConsoleService(args)
    assert s.auth_mode == "irc_ops"
    assert s.channel_commands is False
    m = s.members
    m.apply_names("@simon stranger")
    m.mark_synced()
    assert s.core.auth.allow("simon")  # op, not in any list
    assert not s.core.auth.allow("stranger")  # operators.txt / --operators grant nothing
    m.on_mode(s.channel, "+h", ["stranger"])
    assert s.core.auth.allow("stranger")  # half-ops in the control channel does
    lines = ac.legacy_operator_input_log_lines(args, {"auth_mode": "operators"})
    assert any("--operators-file" in ln for ln in lines)
    assert any("auth_mode=operators is retired" in ln for ln in lines)


def test_install_and_pack_ship_no_operators_list():
    inst = INSTALL.read_text(encoding="utf-8-sig")
    console = INSTALL_CONSOLE.read_text(encoding="utf-8-sig")
    common = COMMON.read_text(encoding="utf-8-sig")
    pack = PACK.read_text(encoding="utf-8-sig")
    update = UPDATE.read_text(encoding="utf-8-sig")
    start = START.read_text(encoding="utf-8-sig")
    assert "$authMode = 'irc_ops'" in inst
    assert "AuthMode    = 'irc_ops'" in inst
    assert "ignoring AIRC_OPERATORS" in inst
    assert "Resolve-BobiverseAircOperatorNicks" not in inst
    assert "$AuthMode = 'irc_ops'" in console
    assert 'appParams += " --operators-file' not in console
    assert 'appParams += " -OperatorsFile' not in console
    for fn in ("Get-BobiverseAircFleetOperatorRoster", "Resolve-BobiverseAircOperatorNicks",
               "Merge-BobiverseAircOperatorsFile"):
        assert f"function {fn}" not in common
    assert 'Property Id="AIRC_OPERATORS"' not in pack
    assert "Copy-Item" not in pack.split("FR #3639")[1].split("return $stage")[0]
    assert "function Get-AircSelfUpdateOperatorsProperty" not in update
    assert "AIRC_OPERATORS=" not in update
    assert "'--auth-mode', 'irc_ops'" in start
    assert "@('--operators-file'" not in start
    assert "$argsList += '--operators'" not in start
    assert not (ROOT / "airc/config/fleet-operators.txt").exists()
