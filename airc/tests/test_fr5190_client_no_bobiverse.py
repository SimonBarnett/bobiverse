"""FR #5190: client airc joins shop or #wonderland, never auto-joins #bobiverse."""
from __future__ import annotations

from pathlib import Path

import airc_console as ac

AIRC = Path(__file__).resolve().parents[1]
INSTALL = AIRC / "scripts" / "Install-Airc.ps1"
SERVICE = AIRC / "scripts" / "airc_console_service.py"


def test_truncated_windows_name_is_shop_id():
    # NetBIOS COMPUTERNAME is already 15 chars (HRS-PRIORITY-DEV -> HRS-PRIORITY-DE).
    mid = ac.machine_id("HRS-PRIORITY-DE")
    assert mid == "hrs-priority-de"
    assert ac.shop_channel(mid) == "#hrs-priority-de"
    assert ac.machine_console_nick(mid) == "hrs-priority-de_console"


def test_client_default_presence_is_empty(monkeypatch):
    monkeypatch.delenv("AIRC_PRESENCE_CHANNELS", raising=False)
    assert ac.resolve_presence_channels({"profile": "client"}) == []
    # Legacy 3774 airc.json still lists #bobiverse — treat as auto, drop it.
    assert (
        ac.resolve_presence_channels(
            {"profile": "client", "presence_channels": ["#bobiverse"]}
        )
        == []
    )


def test_client_env_may_opt_in_bobiverse(monkeypatch):
    monkeypatch.setenv("AIRC_PRESENCE_CHANNELS", "#bobiverse")
    assert ac.resolve_presence_channels({"profile": "client"}) == ["#bobiverse"]


def test_client_join_shop_only_never_bobiverse():
    auth = ac.AuthPolicy(members=ac.ChannelMemberMap(channel="#hrs-priority-de"))
    core = ac.AircConsoleCore(
        machine="hrs-priority-de",
        auth=auth,
        nick="hrs-priority-de_console",
        channel_commands=True,
        presence_channels=[],
    )
    core.channel = "#hrs-priority-de"
    cmds = core.join_commands()
    assert cmds == ["JOIN #hrs-priority-de"]
    joined = cmds[0].split(" ", 1)[1].lower()
    assert "#bobiverse" not in joined.split(",")


def test_client_join_wonderland_when_no_shop():
    auth = ac.AuthPolicy(members=ac.ChannelMemberMap(channel="#wonderland"))
    core = ac.AircConsoleCore(
        machine="hrs-priority-de",
        auth=auth,
        nick="hrs-priority-de_console",
        channel_commands=True,
        presence_channels=[],
    )
    core.channel = "#wonderland"
    cmds = core.join_commands()
    assert cmds == ["JOIN #wonderland"]
    assert "#bobiverse" not in cmds[0].lower()


def test_install_client_does_not_write_bobiverse_presence():
    t = INSTALL.read_text(encoding="utf-8-sig")
    assert "presence_channels" in t
    assert "@('#bobiverse')" not in t
    assert "FR #5190" in t
    assert "5190" in SERVICE.read_text(encoding="utf-8")
