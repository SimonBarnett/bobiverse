# -*- coding: utf-8 -*-
"""FR #9821 / BOB-G1 shared gate: held fr-digest blocks Depends-on children.

Chair offer / assign / !bored / !list / digest ``offerable_count`` share
``gitclaim.depends_gate_reason`` (FR #9455 / #9553). This module is the tip
marker the token-free ``fr_digest`` monitor looks for (``product_on_tip``),
plus small helpers for intake Digest filing (default ``hold``).

Predicate (FR #9821):
* OPEN Depends-on target with labels ``fr-digest`` (or ``digest`` / Kind stamp)
  **and** ``hold`` / ``on-hold`` → child is not offerable (``depends-held``).
* Same digest without ``hold`` → soft-allow while OPEN (``ok-fr-digest``).
* Digests are created with ``hold``; unhold releases children.

FR #9854: tip-priority siblings that must merge while the digest stays held are
list-only on the digest body — ``stamp_digest_depends_on(..., tip_priority=True)``
returns False so filings do not stamp ``Depends-on: #<digest>``.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

DIGEST_LABELS = frozenset({"fr-digest", "digest"})
HOLD_LABELS = frozenset({"hold", "on-hold"})
DIGEST_KIND_RE = re.compile(
    # Parity with gitclaim.DIGEST_KIND_BODY_RE (optional bold/backtick around Kind / colon).
    r"(?im)^[^\S\n]*(?:\*{0,2}|`{0,2})Kind(?:\*{0,2}|`{0,2})[^\S\n]*:"
    r"(?:\*{0,2}|`{0,2})?[^\S\n]*(fr-digest|digest)\b"
)
DIGEST_TITLE_RE = re.compile(r"(?i)^\s*Digest\s*:")


def _label_names(labels: Any) -> set[str]:
    names: set[str] = set()
    if isinstance(labels, str):
        labels = [part.strip() for part in labels.split(",") if part.strip()]
    if not isinstance(labels, (list, tuple)):
        return names
    for item in labels:
        if isinstance(item, str):
            n = item.strip().lower()
        elif isinstance(item, dict):
            n = str(item.get("name") or "").strip().lower()
        else:
            n = ""
        if n:
            names.add(n)
    return names


def is_digest_filing(*, title: str = "", body: str = "", labels: Iterable[str] | None = None) -> bool:
    """True when intake / create should treat the issue as a Digest parent."""
    labs = _label_names(list(labels or ()))
    if labs & DIGEST_LABELS:
        return True
    if DIGEST_KIND_RE.search(str(body or "")):
        return True
    if DIGEST_TITLE_RE.match(str(title or "")):
        return True
    return False


def is_held_fr_digest(*, title: str = "", body: str = "", labels: Any = None) -> bool:
    """True for an OPEN digest that still carries hold / on-hold."""
    labs = _label_names(labels)
    if not (labs & HOLD_LABELS):
        return False
    if labs & DIGEST_LABELS:
        return True
    if DIGEST_KIND_RE.search(str(body or "")):
        return True
    # Title alone is not enough for the live gate (BOB-G3); filing helper may
    # still stamp fr-digest from a Digest: title via ensure_digest_hold_labels.
    return False


def ensure_digest_hold_labels(
    labels: Iterable[str] | None,
    *,
    title: str = "",
    body: str = "",
) -> list[str]:
    """FR #9821: Digest parents get ``fr-digest`` + ``digest`` + ``hold`` by default.

    Preserves caller order; appends missing digest/hold labels. Non-digest
    filings are returned unchanged.
    """
    raw = [str(x).strip() for x in (labels or []) if str(x).strip()]
    if not is_digest_filing(title=title, body=body, labels=raw):
        return raw
    lower = {x.lower() for x in raw}
    out = list(raw)
    if "fr-digest" not in lower:
        out.append("fr-digest")
        lower.add("fr-digest")
    if "digest" not in lower:
        out.append("digest")
        lower.add("digest")
    if "hold" not in lower and "on-hold" not in lower:
        out.append("hold")
    return out


def bob_g1_skip_held_digest() -> str:
    """Stable marker string; ``fr_digest`` monitor greps gitclaim + this module."""
    return "bob_g1_skip_held_digest"


# Digest body section markers (FR #9854). Tip-priority siblings are listed here
# without a child-body Depends-on while the digest stays held.
TIP_PRIORITY_SECTION = "### Tip-priority siblings (LIST ONLY"
CHILDREN_SECTION = "### Children (Depends-on this digest)"


def stamp_digest_depends_on(*, digest_held: bool, tip_priority: bool = False) -> bool:
    """FR #9854: whether a filing should stamp ``Depends-on: #<digest>``.

    Tip-blocking FIX/MRB that must merge while a lessons digest stays held are
    **list-only** on the digest body (Tip-priority siblings). Stamping
    ``Depends-on`` would trip the held-digest gate (#9821) and starve the tip
    merge. Ordinary parked children still stamp Depends-on. After unhold,
    tip-priority siblings may take Depends-on like any other child.
    """
    if tip_priority and digest_held:
        return False
    return True
