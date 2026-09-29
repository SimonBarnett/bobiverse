"""bob-* ChanServ registration for #{machine} (FR #313).

After JOIN, a ``bob-{machine}`` ear must REGISTER its shop channel with
ChanServ so founder/op persists when the channel empties (Ergo otherwise
only ops the creator of an empty ephemeral channel).

Requires Ergo ``channels.registration.enabled: true`` and a logged-in
services account (``accounts.authentication-enabled``). Account
self-registration may be enabled on the private fleet Ergo, or an oper
can ``NickServ SAREGISTER`` the bob-* account first.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Iterable

import shop_ops  # noqa: E402


def ensure_bob_nickserv_password(home: Path | str, *, mint: bool = True) -> str | None:
    """Load or mint ``<home>/nickserv.password`` for bob-* services account (FR #313)."""
    path = Path(home) / "nickserv.password"
    env = (os.environ.get("AGENTIC_IRC_NICKSERV_PASSWORD") or "").strip()
    if env:
        return env
    if path.is_file():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    if not mint:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    secret = str(uuid.uuid4())
    path.write_text(secret + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return secret


def chanserv_register_line(channel: str) -> str:
    """Raw PRIVMSG for ChanServ REGISTER of a shop channel."""
    # First line / first token only — block CR/LF smuggling into a second verb.
    raw = (channel or "").replace("\r", "\n").split("\n", 1)[0].strip()
    ch = raw.split()[0] if raw else ""
    if not ch.startswith("#"):
        raise ValueError("channel must start with #")
    return f"PRIVMSG ChanServ :REGISTER {ch}"


def should_register_shop(own_nick: str, joined_channels: Iterable[str]) -> str | None:
    """Return shop channel to REGISTER, or None if this nick must not.

    Only ``bob-*`` ears register, and only their own ``#{machine}``, and only
    when that shop appears in the JOIN list for this session.
    """
    shop = shop_ops.own_shop(own_nick)
    if not shop:
        return None
    joined = {(c or "").strip().lower() for c in joined_channels}
    if shop.lower() not in joined:
        return None
    return shop


def register_lines_for_bob(own_nick: str, joined_channels: Iterable[str]) -> list[str]:
    """Zero or one ChanServ REGISTER line for a bob-* session."""
    shop = should_register_shop(own_nick, joined_channels)
    if not shop:
        return []
    return [chanserv_register_line(shop)]


def nickserv_register_identify_lines(nick: str, password: str, email: str) -> list[str]:
    """Best-effort NickServ IDENTIFY then REGISTER (account prerequisite)."""
    pw = (password or "").replace("\r", "").replace("\n", "").strip()
    n = (nick or "").replace("\r", "").replace("\n", "").strip()
    em = (email or "").replace("\r", "").replace("\n", "").strip()
    if not pw or not n or not em:
        return []
    return [
        f"PRIVMSG NickServ :IDENTIFY {n} {pw}",
        f"PRIVMSG NickServ :REGISTER {pw} {em}",
    ]
