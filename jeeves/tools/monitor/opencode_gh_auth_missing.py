#!/usr/bin/env python3
"""FR #10041: OpenCode gh_auth_missing is not a healthy idle seat."""
from __future__ import annotations

FINGERPRINT = "opencode_gh_auth_missing"
_NEEDLE = "opencode-ready: blocked gh_auth_missing"


def scan_log(text: str, *, machine: str, nick: str, seat_online: bool) -> str | None:
    if not seat_online or not text or _NEEDLE not in text:
        return None
    return "%s:%s:%s" % (FINGERPRINT, machine, nick)
