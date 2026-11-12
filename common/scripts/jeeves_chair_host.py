"""FR #6947: Jeeves chair may run only on the configured host (default walrus).

No CLI --chair-host on seats. Override is env JEEVES_CHAIR_HOST on the chair box
(NSSM / appliance env), never a flag packed into seat installers.
"""
from __future__ import annotations

import os
import platform
import re

DEFAULT_CHAIR_HOST = "walrus"
CHAIR_HOST_ENV = "JEEVES_CHAIR_HOST"
EXIT_WRONG_HOST = 4

_HOST_RE = re.compile(r"[^a-z0-9_-]+")


def normalize_host(raw: str) -> str:
    mid = _HOST_RE.sub("-", (raw or "").strip().lower()).strip("-_")
    return mid


def configured_chair_host(env: dict | None = None) -> str:
    env = env if env is not None else os.environ
    raw = (env.get(CHAIR_HOST_ENV) or "").strip()
    return normalize_host(raw) or DEFAULT_CHAIR_HOST


def this_host_id(env: dict | None = None) -> str:
    env = env if env is not None else os.environ
    raw = (
        (env.get("BOB_MACHINE_ID") or env.get("COMPUTERNAME") or platform.node() or "")
        .strip()
    )
    return normalize_host(raw)


def chair_host_allowed(
    this: str | None = None,
    chair: str | None = None,
    env: dict | None = None,
) -> bool:
    env = env if env is not None else os.environ
    t = this if this is not None else this_host_id(env)
    c = chair if chair is not None else configured_chair_host(env)
    return bool(t) and bool(c) and t == c


def refuse_chair_host_line(
    this: str | None = None,
    chair: str | None = None,
    env: dict | None = None,
) -> str:
    env = env if env is not None else os.environ
    t = this if this is not None else this_host_id(env)
    c = chair if chair is not None else configured_chair_host(env)
    return f"INFO CHAIR_HOST_REFUSED this={t} chair={c} FR #6947"


def chair_nick_in_use_must_exit(is_chair: bool) -> bool:
    """A chair that cannot take the primary nick must exit, never Jeeves_l."""
    return bool(is_chair)


def chair_nick_taken_line(nick: str) -> str:
    n = (nick or "").strip() or "Jeeves"
    return f"INFO CHAIR_NICK_TAKEN abort nick={n} FR #6947 (no suffixed nick)"
