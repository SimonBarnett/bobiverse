"""FR #3774: client presence-only JOIN of #bobiverse (commands stay on control channel)."""
from __future__ import annotations

from pathlib import Path

import airc_console as ac
from repo_layout import ROOT

INSTALL = ROOT / "airc/scripts/Install-Airc.ps1"
POST = ROOT / "common/docs/post-install.md"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"
SERVICE = ROOT / "airc/scripts/airc_console_service.py"


def test_normalize_and_resolve_presence_channels_defaults():
    assert ac.normalize_irc_channel("bobiverse") == "#bobiverse"
    assert ac.normalize_irc_channel("#Bobiverse") == "#bobiverse"
    assert ac.normalize_irc_channel("") == ""

    # Client default: #bobiverse
    assert ac.resolve_presence_channels({"profile": "client"}) == ["#bobiverse"]
    # Fleet / workstation / missing: none
    assert ac.resolve_presence_channels({"profile": "fleet"}) == []
    assert ac.resolve_presence_channels({"profile": "workstation"}) == []
    assert ac.resolve_presence_channels({}) == []

    # Explicit empty list disables client default
    assert ac.resolve_presence_channels(
        {"profile": "client", "presence_channels": []}
    ) == []
    # Explicit list wins (and drops control-channel dupes later at join time)
    assert ac.resolve_presence_channels(
        {"profile": "fleet", "presence_channels": ["#bobiverse", "other"]}
    ) == ["#bobiverse", "#other"]


def test_resolve_presence_channels_env_override(monkeypatch):
    monkeypatch.setenv("AIRC_PRESENCE_CHANNELS", "#bobiverse, #ops")
    assert ac.resolve_presence_channels({"profile": "fleet"}) == [
        "#bobiverse",
        "#ops",
    ]
    monkeypatch.setenv("AIRC_PRESENCE_CHANNELS", "")
    # Empty env string means none (even for client) when key is set
    assert ac.resolve_presence_channels({"profile": "client"}, prefer_env=True) == []


def test_join_commands_includes_presence_not_control_dupe():
    auth = ac.AuthPolicy(members=ac.ChannelMemberMap(channel="#walrus"))
    core = ac.AircConsoleCore(
        machine="walrus",
        auth=auth,
        nick="walrus_console",
        channel_commands=True,
        presence_channels=["#bobiverse", "#walrus", "bobiverse"],
    )
    # control is #walrus
    cmds = core.join_commands()
    assert len(cmds) == 1
    assert cmds[0].startswith("JOIN ")
    parts = cmds[0].split(" ", 1)[1].split(",")
    assert parts[0].lower() == "#walrus"
    assert parts.count("#bobiverse") == 1
    assert "#walrus" in [p.lower() for p in parts]
    # only one walrus
    assert sum(1 for p in parts if p.lower() == "#walrus") == 1


def test_bobiverse_channel_traffic_never_executes_on_client():
    members = ac.ChannelMemberMap(channel="#walrus")
    members.apply_names("@simon")
    members.mark_synced()
    auth = ac.AuthPolicy(members=members, self_nicks={"walrus_console"})
    replies: list[str] = []
    runner = ac.ShellJobRunner(
        on_reply=lambda n, line: replies.append(line), wait=True
    )
    core = ac.AircConsoleCore(
        machine="walrus",
        auth=auth,
        nick="walrus_console",
        shell_runner=runner,
        channel_commands=True,
        presence_channels=["#bobiverse"],
    )
    # Presence channel: ignore even from +o
    hr = core.handle_raw(
        ":simon!u@h PRIVMSG #bobiverse :cmd: echo should-not-run"
    )
    assert hr is not None
    assert hr.action == "silent_channel"
    assert replies == []

    # Control channel: still runs
    hr2 = core.handle_raw(
        ":simon!u@h PRIVMSG #walrus :Write-Output 'fr3774-ok'"
    )
    assert hr2 is not None
    assert hr2.action == "shell"
    assert any("fr3774-ok" in r or r.endswith("fr3774-ok") for r in replies)
    assert any(r.startswith("DONE id=") and r.endswith("exit=0") for r in replies)


def test_same_irc_channel_helper():
    assert ac.same_irc_channel("#Walrus", "walrus")
    assert not ac.same_irc_channel("#bobiverse", "#walrus")


def test_docs_and_install_mention_presence_channels():
    install = INSTALL.read_text(encoding="utf-8")
    assert "presence_channels" in install
    assert "3774" in install or "FR #3774" in install
    post = POST.read_text(encoding="utf-8")
    assert "presence_channels" in post or "#bobiverse" in post
    assert "3774" in post
    skill = SKILL.read_text(encoding="utf-8")
    assert "presence" in skill.lower() or "3774" in skill
    svc = SERVICE.read_text(encoding="utf-8")
    assert "same_irc_channel" in svc or "FR #3774" in svc
    assert "presence_channels" in svc
