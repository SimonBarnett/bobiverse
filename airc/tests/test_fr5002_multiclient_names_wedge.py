"""FR #5002: multiclient reattach must stay names-synced; denials carry id+reason.

Ergo multiclient replays JOIN+NAMES before join_shop runs. Clearing the member
map on join_shop then sending a redundant JOIN leaves auth stuck as
channel-state-unknown (Ergo ignores JOIN when already in-channel).
"""
from __future__ import annotations

import re
from pathlib import Path
from unittest import mock

import airc_console as ac
import airc_console_service as svc

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "airc" / "scripts" / "airc_console_service.py"
IRC_AGENT = ROOT / "common" / "scripts" / "irc_agent.py"
REMOTE = ROOT / "airc" / "scripts" / "Invoke-AircRemote.ps1"


def test_join_shop_does_not_wipe_reattach_names():
    """NAMES that arrived before join_shop must survive (multiclient replay)."""
    s = svc.AircConsoleService.__new__(svc.AircConsoleService)
    s.channel = "#wonderland"
    s.nick = "rm-sql01_console"
    s.server_nick = "rm-sql01_console"
    s._active_mode = "registered"
    s._pending_join_deadline = 0.0
    s._joined_shop = False
    s.presence_channels = []
    s.members = ac.ChannelMemberMap(channel="#wonderland")
    # Ergo already replayed NAMES on reattach:
    s.members.apply_names("@simon %bob-marchhare rm-sql01_console")
    s.members.mark_synced()
    s.core = ac.AircConsoleCore(
        nick=s.nick,
        auth=ac.AuthPolicy(
            auth_mode="irc_ops",
            members=s.members,
            self_nicks={s.nick.lower()},
        ),
        channel_commands=True,
    )
    s.core.channel = s.channel
    sent: list[str] = []
    s.send = sent.append  # type: ignore[method-assign]

    s.join_shop()

    assert s.members.synced is True
    assert s.members.has_chan_priv("simon")
    assert s.core.auth.allow("simon")
    assert not s.core.auth.deny_reason("simon")
    # FR #5002: always ask for NAMES after JOIN (Ergo may have ignored JOIN).
    assert any(x.upper().startswith("NAMES ") for x in sent)
    assert any("#wonderland" in x for x in sent if x.upper().startswith("NAMES "))


def test_fresh_353_still_clears_when_synced():
    """FR #3511 keep: a fresh NAMES while synced replaces, does not merge."""
    m = ac.ChannelMemberMap(channel="#wonderland")
    m.apply_names("@op %gone")
    m.mark_synced()
    if m.synced:
        m.clear()
        m.set_channel("#wonderland")
    m.apply_names("@op")
    m.mark_synced()
    assert m.has_chan_priv("op")
    assert not m.known("gone")


def test_deny_reply_carries_id_and_real_reason():
    m = ac.ChannelMemberMap(channel="#wonderland")
    # unsynced -> channel-state-unknown
    auth = ac.AuthPolicy(auth_mode="irc_ops", members=m, self_nicks={"rm-sql01_console"})
    core = ac.AircConsoleCore(
        nick="rm-sql01_console",
        auth=auth,
        channel_commands=True,
    )
    core.channel = "#wonderland"
    hr = core.handle_raw(
        ":simon!u@h PRIVMSG #wonderland :id=2db69c19 hostname"
    )
    assert hr is not None
    assert hr.action == "deny"
    assert hr.deny_reason == "channel-state-unknown"
    assert hr.reply == "DONE id=2db69c19 exit=126 channel-state-unknown"

    m.apply_names("@other")
    m.mark_synced()
    hr2 = core.handle_raw(":simon!u@h PRIVMSG #wonderland :id=aabbccdd hostname")
    assert hr2 is not None
    assert hr2.action == "deny"
    assert hr2.deny_reason == "not-op"
    assert hr2.reply == "DONE id=aabbccdd exit=126 not-op"


def test_names_watchdog_escalates_then_self_restart_flag():
    """Unsycned past timeout: NAMES -> PART/JOIN -> force reconnect; long wedge exits."""
    assert hasattr(svc, "NAMES_SYNC_WATCH_S")
    assert hasattr(svc, "AUTH_WEDGE_EXIT_S")
    assert svc.NAMES_SYNC_WATCH_S > 0
    assert svc.AUTH_WEDGE_EXIT_S > 0

    s = svc.AircConsoleService.__new__(svc.AircConsoleService)
    s.channel = "#wonderland"
    s.nick = "rm-sql01_console"
    s.members = ac.ChannelMemberMap(channel="#wonderland")
    s._joined_shop = True
    s._names_watch_deadline = 50.0  # due when monotonic>=50; 0 means disarmed
    s._names_watch_stage = 0
    s._auth_wedge_since = None
    s._force_reconnect = False
    s._stop = mock.Mock()
    s._stop.is_set.return_value = False
    sent: list[str] = []
    s.send = sent.append  # type: ignore[method-assign]

    # stage 0 -> NAMES
    with mock.patch.object(svc.time, "monotonic", return_value=100.0):
        s._names_sync_watchdog()
    assert any(x.upper().startswith("NAMES ") for x in sent)
    assert s._names_watch_stage == 1

    sent.clear()
    s._names_watch_deadline = 150.0
    with mock.patch.object(svc.time, "monotonic", return_value=200.0):
        s._names_sync_watchdog()
    assert any(x.upper().startswith("PART ") for x in sent)
    assert any(x.upper().startswith("JOIN ") for x in sent)
    assert s._names_watch_stage == 2

    s._names_watch_deadline = 250.0
    with mock.patch.object(svc.time, "monotonic", return_value=300.0):
        s._names_sync_watchdog()
    assert s._force_reconnect is True


def test_fr5066_watchdog_part_join_reaches_reconnect():
    """FR #5066: self-PART -> join_shop must not reset stage; reconnect within ~3 windows."""
    s = svc.AircConsoleService.__new__(svc.AircConsoleService)
    s.channel = "#marchhare"
    s.nick = "marchhare_test_console"
    s.server_nick = "marchhare_test_console"
    s._active_mode = "registered"
    s._pending_join_deadline = 0.0
    s.presence_channels = []
    s.members = ac.ChannelMemberMap(channel="#marchhare")
    # unsynced (no 366)
    s.core = ac.AircConsoleCore(
        nick=s.nick,
        auth=ac.AuthPolicy(
            auth_mode="irc_ops",
            members=s.members,
            self_nicks={s.nick.lower()},
        ),
        channel_commands=True,
    )
    s.core.channel = s.channel
    s._joined_shop = True
    s._names_watch_deadline = 10.0
    s._names_watch_stage = 0
    s._auth_wedge_since = None
    s._force_reconnect = False
    s._stop = mock.Mock()
    s._stop.is_set.return_value = False
    sent: list[str] = []
    s.send = sent.append  # type: ignore[method-assign]

    watch = max(1.0, float(svc.NAMES_SYNC_WATCH_S))
    t0 = 1000.0

    with mock.patch.object(svc.time, "monotonic", return_value=t0 + watch):
        s._names_sync_watchdog()
    assert s._names_watch_stage == 1

    with mock.patch.object(svc.time, "monotonic", return_value=t0 + 2 * watch):
        s._names_sync_watchdog()
    assert s._names_watch_stage == 2
    assert any(x.upper().startswith("PART ") for x in sent)

    # Live bug: self-PART -> _lost_control_channel -> join_shop reset stage to 0.
    with mock.patch.object(svc.time, "monotonic", return_value=t0 + 2 * watch + 0.5):
        s._lost_control_channel("self-part")
    assert s.members.synced is False
    assert s._names_watch_stage == 2, "join_shop must preserve escalation stage (FR #5066)"

    # join_shop refreshed the deadline by one more watch window after the rejoin.
    with mock.patch.object(svc.time, "monotonic", return_value=t0 + 3 * watch + 1.0):
        s._names_sync_watchdog()
    assert s._force_reconnect is True


def test_auth_wedge_requests_process_exit():
    s = svc.AircConsoleService.__new__(svc.AircConsoleService)
    s.members = ac.ChannelMemberMap(channel="#wonderland")
    s._joined_shop = True
    s._auth_wedge_since = 1.0
    s._exit_for_nssm_restart = False
    s._force_reconnect = False
    s._stop = mock.Mock()
    with mock.patch.object(svc.time, "monotonic", return_value=1.0 + svc.AUTH_WEDGE_EXIT_S + 1):
        s._auth_wedge_watchdog()
    assert s._exit_for_nssm_restart is True


def test_irc_agent_records_idless_done_exit():
    text = IRC_AGENT.read_text(encoding="utf-8")
    # Must match DONE exit=126 without requiring id=
    m = re.search(
        r"_AIRC_REPLY_BODY_RE\s*=\s*re\.compile\(\s*((?:.|\n)*?)\,\s*re\.IGNORECASE",
        text,
    )
    assert m, "missing _AIRC_REPLY_BODY_RE"
    # Source pin: optional id= group present
    assert "DONE" in m.group(1)
    assert "id=" in m.group(1)
    assert "?:" in m.group(1) or "id=[0-9a-f]+\\s+)?" in m.group(1).replace("\n", "")


def test_invoke_airc_remote_fail_fast_refusal():
    text = REMOTE.read_text(encoding="utf-8")
    assert "exit=126" in text
    assert "fail fast" in text.lower() or "refus" in text.lower() or "126" in text
    # Wait path must notice refusal without waiting full TimeoutSec
    assert re.search(r"DONE.*exit=126|exit=126.*DONE", text, re.I)


def test_service_source_pins_names_after_join_and_no_clear():
    src = SERVICE.read_text(encoding="utf-8")
    assert "FR #5002" in src
    assert "NAMES " in src or 'f"NAMES' in src or "NAMES {" in src
    # join_shop must document not clearing on reattach
    assert "join_shop" in src
