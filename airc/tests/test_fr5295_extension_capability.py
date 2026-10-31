"""FR #5295: EXTENSION capability + client/workstation policy (exit=126)."""
from __future__ import annotations

from pathlib import Path

import airc_console as ac
from airc_auth_helpers import ops_auth
from repo_layout import ROOT

INSTALL = ROOT / "airc/scripts/Install-Airc.ps1"
PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"
POST = ROOT / "common/docs/post-install.md"


def _core(**kw):
    auth = ops_auth("op", channel="#tm")
    return ac.AircConsoleCore(machine="tm", auth=auth, nick="tm_console", **kw)


def test_fr5295_extension_off_done_126():
    core = _core(capabilities=ac.ConsoleCapabilities(extension="off"))
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :EXTENSION install")
    assert hr is not None
    assert hr.action == "capability_deny"
    assert hr.reply == "DONE exit=126 extension-disabled"


def test_fr5295_shell_off_still_shell_disabled():
    core = _core(
        capabilities=ac.ConsoleCapabilities(shell_mode="off", extension="on")
    )
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :EXTENSION status")
    assert hr is not None
    assert hr.action == "capability_deny"
    assert hr.reply == "DONE exit=126 shell-disabled"


def test_fr5295_update_off_still_refuses():
    core = _core(
        capabilities=ac.ConsoleCapabilities(update="off", extension="on")
    )
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :EXTENSION install")
    assert hr is not None
    assert hr.action == "capability_deny"
    assert hr.reply == "DONE exit=126 update-disabled"


def test_fr5295_unauthorized_not_op():
    core = _core(capabilities=ac.ConsoleCapabilities(extension="on"))
    hr = core.handle_raw(":evil!u@h PRIVMSG tm_console :EXTENSION install")
    assert hr is not None and hr.action == "deny"
    assert "126" in (hr.reply or "") or "not-op" in (hr.reply or "").lower()


def test_fr5295_fleet_on_accepts():
    core = _core(capabilities=ac.ConsoleCapabilities(extension="on"))
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :EXTENSION status")
    assert hr is not None and hr.action == "extension"
    assert "EXTENSION accepted" in (hr.reply or "")


def test_fr5295_help_lists_extension_cap():
    core = _core(capabilities=ac.ConsoleCapabilities(extension="off"))
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :!help")
    assert "extension=off" in (hr.reply or "")


def test_fr5295_load_capabilities_profile_defaults(tmp_path: Path):
    cfg = tmp_path / "config" / "airc.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('{"profile":"client","shell":"operators","update":"on"}\n', encoding="utf-8")
    caps = ac.load_capabilities(
        install_root=tmp_path, cli_shell=None, cli_jobs=None, cli_update=None
    )
    assert caps.extension == "off"
    cfg.write_text(
        '{"profile":"client","extension":"on","shell":"operators"}\n',
        encoding="utf-8",
    )
    caps2 = ac.load_capabilities(
        install_root=tmp_path,
        cli_shell=None,
        cli_jobs=None,
        cli_update=None,
        cli_extension="off",
    )
    assert caps2.extension == "off"
    cfg.write_text('{"profile":"fleet"}\n', encoding="utf-8")
    caps3 = ac.load_capabilities(install_root=tmp_path)
    assert caps3.extension == "on"


def test_fr5295_resolve_install_defaults():
    assert (
        ac.resolve_extension_cap_for_install(
            prior="on", explicit=None, profile="workstation"
        )
        == "off"
    )
    assert (
        ac.resolve_extension_cap_for_install(
            prior="on", explicit=None, profile="client"
        )
        == "off"
    )
    assert (
        ac.resolve_extension_cap_for_install(
            prior=None, explicit="on", profile="client"
        )
        == "on"
    )
    assert (
        ac.resolve_extension_cap_for_install(prior=None, explicit=None, profile=None)
        == "on"
    )


def test_fr5295_docs_and_pack_wire():
    inst = INSTALL.read_text(encoding="utf-8")
    pack = PACK.read_text(encoding="utf-8")
    skill = SKILL.read_text(encoding="utf-8")
    post = POST.read_text(encoding="utf-8")
    assert not INSTALL.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "ExtensionCap" in inst
    assert "$resolvedExtension = 'off'" in inst
    assert "AIRC_EXTENSION" in pack
    assert "-ExtensionCap" in pack
    assert "AIRC_EXTENSION" in post
    assert "FR #5295" in skill
    assert "extension-disabled" in skill
    needle = "FR #5295: dedicated"
    assert needle in skill
    i = skill.find(needle)
    assert "\u2014" not in skill[i : i + 220]
