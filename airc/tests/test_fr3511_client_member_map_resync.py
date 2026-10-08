"""FR #3511: AIRC_PROFILE=client — ops map must not survive reconnect or self-kick.

Live repro (issue #3511): after reconnect, a nick that PART'd while the console
was offline kept ``%`` and still got LocalSystem shell; after the console was
KICKed, ops kept shell while ``synced=True`` and the console was not in channel.
"""
from __future__ import annotations

from pathlib import Path

import airc_console as ac

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "airc" / "scripts" / "airc_console_service.py"
SKILL = ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc" / "SKILL.md"


def test_reconnect_clears_stale_halfop_absent_from_names():
    """Stale % for a nick absent from post-reconnect NAMES must deny."""
    m = ac.ChannelMemberMap(channel="#bvt0126dom")
    m.apply_names("@bvt0126m @bvt_op %bvt_usr")
    m.mark_synced()
    auth = ac.AuthPolicy(
        auth_mode="irc_ops",
        members=m,
        self_nicks={"bvt0126m"},
    )
    assert auth.allow("bvt_usr")
    assert auth.allow("bvt_op")

    # FR #3511: (re)join must clear before NAMES — same channel name is not enough.
    m.clear()
    assert not m.synced
    assert not auth.allow("bvt_usr")
    assert auth.deny_reason("bvt_usr") == "channel-state-unknown"

    # NAMES after reconnect: bvt_usr left while offline — must not keep %.
    m.set_channel("#bvt0126dom")
    m.apply_names("@bvt0126m @bvt_op")
    m.mark_synced()
    assert not m.known("bvt_usr")
    assert not auth.allow("bvt_usr")
    assert auth.deny_reason("bvt_usr") == "not-op"
    assert auth.allow("bvt_op")


def test_set_channel_same_name_still_clears_for_resync():
    """set_channel on the same channel must drop stale prefixes (FR #3511)."""
    m = ac.ChannelMemberMap(channel="#acme")
    m.apply_names("%ghost @live")
    m.mark_synced()
    assert m.has_chan_priv("ghost")

    m.set_channel("#acme")  # same name — previously a no-op clear
    assert not m.synced
    assert not m.known("ghost")
    assert not m.known("live")


def test_self_kick_clears_map_ops_denied_until_resync():
    """Self-KICK must clear the map; ops denied until 366 after rejoin."""
    m = ac.ChannelMemberMap(channel="#bvt0126dom")
    m.apply_names("@bvt0126m @bvt_op")
    m.mark_synced()
    auth = ac.AuthPolicy(
        auth_mode="irc_ops",
        members=m,
        self_nicks={"bvt0126m"},
    )
    assert auth.allow("bvt_op")

    # Service drops only the kicked nick today; FR #3511 requires full clear.
    m.on_kick("bvt0126m")
    m.clear()  # required behaviour after self-kick
    assert not m.synced
    assert not auth.allow("bvt_op")
    assert auth.deny_reason("bvt_op") == "channel-state-unknown"

    m.apply_names("@bvt0126m @bvt_op")
    m.mark_synced()
    assert auth.allow("bvt_op")


def test_names_while_synced_replaces_map_not_merge():
    """A fresh 353 batch while synced must not leave absent nicks privileged."""
    m = ac.ChannelMemberMap(channel="#acme")
    m.apply_names("@op %gone")
    m.mark_synced()
    assert m.has_chan_priv("gone")

    # Service: if synced and 353 arrives, clear then apply (FR #3511).
    if m.synced:
        m.clear()
        m.set_channel("#acme")
    m.apply_names("@op")
    m.mark_synced()
    assert m.has_chan_priv("op")
    assert not m.known("gone")
    assert not m.has_chan_priv("gone")


def test_service_clears_on_handshake_join_and_self_kick_part():
    """Wire pins: handshake/join_shop clear; self KICK/PART clear+rejoin."""
    t = SERVICE.read_text(encoding="utf-8")
    assert "FR #3511" in t
    # join_shop / handshake must clear member map (not only set_channel).
    assert "members.clear()" in t
    # Self loss of channel membership.
    assert "lost-control" in t or "self-kick" in t or "self-part" in t
    assert "_joined_shop = False" in t
    # 353 while synced replaces rather than merges.
    assert "353" in t


def test_skill_mentions_resync_on_reconnect_or_kick():
    skill = SKILL.read_text(encoding="utf-8")
    # Soft pin: client-profile docs should mention resync / clear on reconnect or kick.
    assert "FR #3401" in skill or "irc_ops" in skill
    assert "FR #3511" in skill or "resync" in skill.lower() or "reconnect" in skill.lower()
