"""FR #5272: fleet public HTTP base (webhooks), separate from IRC host.

IRC stays on irc.ntsa.uk (TLS 993/6697). Digest/intake/git/jira/hours HTTP
defaults to https://bob.ntsa.uk so Cloudflare can proxy walrus without
greying IRC DNS.
"""
from __future__ import annotations

import os

DEFAULT_PUBLIC_BASE = "https://bob.ntsa.uk"
PUBLIC_BASE_ENV = "BOB_PUBLIC_BASE"
# IRC hostname is intentionally separate and not overridden by BOB_PUBLIC_BASE.
DEFAULT_IRC_HOST = "irc.ntsa.uk"


def public_base(env: dict[str, str] | None = None) -> str:
    """Return the fleet public HTTP origin (no trailing slash)."""
    src = env if env is not None else os.environ
    raw = (src.get(PUBLIC_BASE_ENV) or "").strip().rstrip("/")
    return raw or DEFAULT_PUBLIC_BASE


def public_url(path: str, *, env: dict[str, str] | None = None) -> str:
    """Join public_base with a path (e.g. /bob/v1/report)."""
    base = public_base(env)
    p = (path or "").strip()
    if not p:
        return base
    if not p.startswith("/"):
        p = "/" + p
    return base + p


def default_digest_url(env: dict[str, str] | None = None) -> str:
    return public_url("/bob/v1/report", env=env)


def default_intake_url(env: dict[str, str] | None = None) -> str:
    return public_url("/bob/v1/intake", env=env)


def default_git_hook_url(env: dict[str, str] | None = None) -> str:
    return public_url("/bob/v1/git", env=env)
