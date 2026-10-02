"""FR #224: worker seats never PRIVMSG a nick — channel-only shop output.

Workers ``{machine}-{pid}`` and legacy ``w-<short>-<pid>`` publish only to
their own ``#{machine}``. Chair (Jeeves) may still PM for ``!list`` / ``!help``.
bob-* ears are not workers under this rule (they may whisper fleet JSON).
"""

from __future__ import annotations

import re
from typing import Callable

import bobreport
import talk_seat_pid

# PRIVMSG target :text  (target may be channel or nick)
_PRIVMSG_HEAD = re.compile(r"^PRIVMSG\s+(\S+)\s+:?(.*)$", re.IGNORECASE | re.DOTALL)

FORBIDDEN_NICK_EXAMPLES = (
    "bob-marchhare",
    "bob-flamingo",
    "simon",
    "Jeeves",
    "jeeves",
)


def is_channel_only_worker_nick(nick: str) -> bool:
    """True for live watch/talk seats and legacy w-* shop workers."""
    n = (nick or "").strip()
    if not n:
        return False
    if talk_seat_pid.parse_talk_seat_nick(n) is not None:
        return True
    if bobreport.parse_worker_nick(n) is not None:
        return True
    # Also accept {machine}-{pid} even if machine not in FLEET table yet
    if bobreport.parse_talk_seat_nick(n) is not None:
        return True
    return False


def is_nick_privmsg_target(target: str) -> bool:
    """True when PRIVMSG target is a nick (not a channel)."""
    t = (target or "").strip()
    if not t or t.startswith("#"):
        return False
    # multi-target rare; treat as nick path if no leading #
    if "," in t:
        parts = [p.strip() for p in t.split(",") if p.strip()]
        return any(not p.startswith("#") for p in parts)
    return True


def worker_own_shop(nick: str) -> str | None:
    """#{machine} for a channel-only worker nick."""
    parsed = talk_seat_pid.parse_talk_seat_nick(nick)
    if parsed:
        return bobreport.shop_channel(parsed[0])
    mid = bobreport.parse_talk_seat_nick(nick)
    if mid:
        return bobreport.shop_channel(mid)
    w = bobreport.parse_worker_nick(nick)
    if w:
        return bobreport.shop_channel(w[0])
    return None


def parse_privmsg_line(line: str) -> tuple[str, str] | None:
    """Return (target, text) for a PRIVMSG wire/outbox line."""
    s = (line or "").strip()
    if not s.upper().startswith("PRIVMSG "):
        return None
    m = _PRIVMSG_HEAD.match(s)
    if not m:
        return None
    return m.group(1).strip(), m.group(2)


def rewrite_worker_outbound_line(sender_nick: str, line: str) -> str:
    """
    If sender is a channel-only worker and line is PRIVMSG <nick> :...,
    rewrite target to the worker's own shop channel. Channels pass through.
    Non-PRIVMSG pass through.
    """
    if not is_channel_only_worker_nick(sender_nick):
        return line
    parsed = parse_privmsg_line(line)
    if not parsed:
        return line
    target, text = parsed
    if not is_nick_privmsg_target(target):
        return line
    shop = worker_own_shop(sender_nick)
    if not shop:
        # drop nick PM rather than leak — empty channel unknown
        return f"PRIVMSG #unknown :{text}"
    return f"PRIVMSG {shop} :{text}"


def assert_no_worker_nick_privmsg(
    sender_nick: str,
    lines: list[str],
    *,
    forbidden_targets: tuple[str, ...] = FORBIDDEN_NICK_EXAMPLES,
) -> list[str]:
    """
    Return list of violating lines (empty if ok).
    Used by tests: any worker PRIVMSG to a nick fails.
    """
    if not is_channel_only_worker_nick(sender_nick):
        return []
    bad: list[str] = []
    for line in lines:
        parsed = parse_privmsg_line(line)
        if not parsed:
            continue
        target, _text = parsed
        if is_nick_privmsg_target(target):
            bad.append(line)
            continue
        # also catch if rewritten failed and still hits known nicks
        tl = target.lower()
        for ft in forbidden_targets:
            if tl == ft.lower():
                bad.append(line)
    return bad
