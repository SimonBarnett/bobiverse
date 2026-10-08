"""docs/mrb-3523 hostile pins for FR #3511 / PR #3523 irc_ops member-map resync."""
from __future__ import annotations

from pathlib import Path

import airc_console as ac

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "airc" / "scripts" / "airc_console_service.py"
CONSOLE = ROOT / "airc" / "scripts" / "airc_console.py"
SKILL = ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc" / "SKILL.md"


def test_set_channel_source_always_clears_no_same_name_gate():
    """Hostile: set_channel must clear unconditionally (no same-name skip)."""
    src = CONSOLE.read_text(encoding="utf-8")
    i = src.find("def set_channel")
    j = src.find("def apply_names", i)
    chunk = src[i:j]
    assert "FR #3511" in chunk
    assert "self.clear()" in chunk
    assert "if ch.lower() !=" not in chunk


def test_service_wires_lost_control_from_self_part_and_kick():
    """Hostile: self PART/KICK must call _lost_control_channel (clear+rejoin)."""
    t = SERVICE.read_text(encoding="utf-8")
    assert "def _lost_control_channel" in t
    assert '_lost_control_channel("self-part")' in t
    assert '_lost_control_channel("self-kick")' in t
    assert "lost-control" in t
    assert "_joined_shop = False" in t
    # handshake clears before any reconnect NAMES
    assert "FR #3511" in t
    assert "members.clear()" in t


def test_353_while_synced_clears_before_apply_names():
    """Hostile: unexpected 353 while synced replaces the map."""
    t = SERVICE.read_text(encoding="utf-8")
    # Contiguous intent: synced → clear → set_channel before apply_names
    i = t.find("if cmd == \"353\"")
    assert i > 0
    chunk = t[i : i + 500]
    assert "if self.members.synced" in chunk
    assert "members.clear()" in chunk
    assert "apply_names" in chunk


def test_behaviour_set_channel_same_name_drops_stale_halfop():
    m = ac.ChannelMemberMap(channel="#bvt")
    m.apply_names("%ghost @op")
    m.mark_synced()
    assert m.has_chan_priv("ghost")
    m.set_channel("#bvt")
    assert not m.synced
    assert not m.known("ghost")
    assert not m.known("op")


def test_skill_client_profile_cites_fr3511_lost_control():
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3511" in skill
    assert "lost-control" in skill or "ChannelMemberMap" in skill
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
