#!/usr/bin/env python3
"""FR #10040: OpenCode Clear TimeoutExpired plus stale no-ACK."""
from __future__ import annotations

import re

FINGERPRINT = "opencode_clear_timeout_no_ack"

_CLEAR = re.compile(r"opencode finish: Clear result=failed:TimeoutExpired")
_STALE = re.compile(r"relay: stale worktree offer .+no ACK yet", re.I)


def scan_log(text: str, *, machine: str, nick: str, turns_empty: bool) -> str | None:
    """Return the fingerprint when Clear timed out and no ACK followed."""
    if not text or not turns_empty:
        return None
    if not _CLEAR.search(text) or not _STALE.search(text):
        return None
    return "%s:%s:%s" % (FINGERPRINT, machine, nick)
