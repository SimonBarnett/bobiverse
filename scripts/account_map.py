"""Nick -> services account map (CAP account-notify / extended-join / account-tag).

FR #230: non-fleet seats filter commands by account, not spoofable nick.
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path

# @account=name or account=name; end before space or next tag
_ACCOUNT_TAG = re.compile(r"(?:^|;)account=([^;\s]*)", re.IGNORECASE)
_PREFIX = re.compile(r"^:([^!\s]+)(?:!([^@\s]*)@(\S+))?")


class AccountMap:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._nick_to_account: dict[str, str] = {}

    def set(self, nick: str, account: str | None) -> None:
        n = (nick or "").strip().lower()
        if not n:
            return
        with self._lock:
            if account is None or account == "" or account == "*":
                self._nick_to_account.pop(n, None)
            else:
                self._nick_to_account[n] = account.strip()

    def get(self, nick: str) -> str | None:
        n = (nick or "").strip().lower()
        with self._lock:
            return self._nick_to_account.get(n)

    def rename(self, old: str, new: str) -> None:
        o = (old or "").strip().lower()
        n = (new or "").strip().lower()
        if not o or not n:
            return
        with self._lock:
            acct = self._nick_to_account.pop(o, None)
            if acct is not None:
                self._nick_to_account[n] = acct

    def clear_nick(self, nick: str) -> None:
        self.set(nick, None)

    def snapshot(self) -> dict[str, str]:
        with self._lock:
            return dict(self._nick_to_account)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.snapshot(), sort_keys=True, indent=0) + "\n", encoding="utf-8")

    def load(self, path: Path) -> None:
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(data, dict):
            return
        with self._lock:
            self._nick_to_account = {
                str(k).lower(): str(v) for k, v in data.items() if k and v and v != "*"
            }


def parse_message_tags(line: str) -> tuple[dict[str, str], str]:
    """Split IRCv3 tags from a raw line. Returns (tags, rest_without_leading_@tags)."""
    if not line.startswith("@"):
        return {}, line
    try:
        tag_part, rest = line[1:].split(" ", 1)
    except ValueError:
        return {}, line
    tags: dict[str, str] = {}
    for piece in tag_part.split(";"):
        if not piece:
            continue
        if "=" in piece:
            k, v = piece.split("=", 1)
            tags[k.lower()] = v
        else:
            tags[piece.lower()] = ""
    return tags, rest


def account_from_tags(tags: dict[str, str]) -> str | None:
    if "account" not in tags:
        return None
    v = tags.get("account") or ""
    if v in ("", "*"):
        return None
    return v


def account_from_tag_string(tag_blob: str) -> str | None:
    m = _ACCOUNT_TAG.search(tag_blob or "")
    if not m:
        return None
    v = m.group(1)
    if v in ("", "*"):
        return None
    return v


def parse_prefix_nick(rest: str) -> str | None:
    if not rest.startswith(":"):
        return None
    m = _PREFIX.match(rest)
    return m.group(1) if m else None


# Caps to request when the server advertises them (alongside sasl).
ACCOUNT_CAPS = ("account-notify", "extended-join", "account-tag")


def select_account_caps(offered: str | set[str]) -> list[str]:
    if isinstance(offered, str):
        toks = {t.lower() for t in offered.replace(":", " ").split() if t}
    else:
        toks = {t.lower() for t in offered}
    return [c for c in ACCOUNT_CAPS if c in toks]
