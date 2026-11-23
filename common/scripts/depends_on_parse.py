"""Depends-on grammar helpers (BOB-D*).

BOB-D2 (FR #8806): relative ``#N`` resolves to the FR's own ``owner/repo#N``.
BOB-D1 will add body parsing beside these helpers.
"""
from __future__ import annotations

import re

_REPO_RX = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_RELATIVE_RX = re.compile(r"^#(\d+)$")
_FULL_RX = re.compile(r"^([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(\d+)$")


def resolve_depends_ref(fr_repo: str, ref: str) -> str:
    """Resolve one Depends-on token to ``owner/repo#N``.

    Relative ``#N`` uses ``fr_repo`` (the FR's own repo). Full
    ``owner/repo#N`` is returned unchanged. Empty / ``(none)`` is not a ref.
    """
    repo = (fr_repo or "").strip()
    token = (ref or "").strip()
    if not repo or not _REPO_RX.match(repo):
        raise ValueError(f"invalid fr_repo: {fr_repo!r}")
    if not token or token.lower() == "(none)":
        raise ValueError(f"not a Depends-on ref: {ref!r}")

    m_rel = _RELATIVE_RX.match(token)
    if m_rel:
        return f"{repo}#{m_rel.group(1)}"

    m_full = _FULL_RX.match(token)
    if m_full:
        return f"{m_full.group(1)}#{m_full.group(2)}"

    raise ValueError(f"unrecognized Depends-on ref: {ref!r}")
