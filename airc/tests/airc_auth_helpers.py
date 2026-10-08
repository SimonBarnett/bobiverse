"""Test helper (FR #3639): build an AuthPolicy from a synced control-channel member map.

airc authorises by live IRC channel status only (+o/+h or higher in the control
channel); there is no operators list. Tests that need an authorised sender give it
ops (``@``) or half-ops (``%``) here instead of seeding an operators set.
"""
from __future__ import annotations

import airc_console as ac


def member_map(*op_nicks: str, halfops: tuple[str, ...] = (), plain: tuple[str, ...] = (),
               voiced: tuple[str, ...] = (), channel: str = "#tm", synced: bool = True) -> ac.ChannelMemberMap:
    m = ac.ChannelMemberMap(channel=channel)
    toks = [f"@{n}" for n in op_nicks] + [f"%{n}" for n in halfops] + [f"+{n}" for n in voiced] + list(plain)
    m.apply_names(" ".join(toks))
    if synced:
        m.mark_synced()
    return m


def ops_auth(*op_nicks: str, halfops: tuple[str, ...] = (), plain: tuple[str, ...] = (),
             voiced: tuple[str, ...] = (), channel: str = "#tm", synced: bool = True,
             self_nicks: set[str] | None = None) -> ac.AuthPolicy:
    return ac.AuthPolicy(
        members=member_map(*op_nicks, halfops=halfops, plain=plain, voiced=voiced,
                           channel=channel, synced=synced),
        self_nicks=set(self_nicks or set()),
    )
