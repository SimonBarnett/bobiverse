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

FR #9848: when the parent digest loses ``hold``, strip ``hold`` / ``on-hold``
from ordinary Depends-on children (not nested digest children — FR #9860).
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

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


def strip_hold_labels(labels: Iterable[str] | None) -> list[str]:
    """FR #9848: drop ``hold`` / ``on-hold`` from a label list (preserve order)."""
    out: list[str] = []
    for raw in labels or []:
        s = str(raw or "").strip()
        if not s:
            continue
        if s.lower() in HOLD_LABELS:
            continue
        out.append(s)
    return out


def should_strip_child_hold_on_parent_unhold(row: Mapping[str, Any] | None) -> bool:
    """True for ordinary FR children; False for nested digests (FR #9860).

    Nested ``fr-digest`` / ``digest`` / ``Kind:`` children keep their own hold
    until an operator unholds that digest explicitly.
    """
    if not isinstance(row, Mapping):
        return False
    title = str(row.get("title") or "")
    body = str(row.get("body") or "")
    labs = _label_names(row.get("labels"))
    if labs & DIGEST_LABELS:
        return False
    if DIGEST_KIND_RE.search(body):
        return False
    if DIGEST_TITLE_RE.match(title) and (labs & HOLD_LABELS):
        # Title Digest: with hold but missing label still treated as nested gate.
        return False
    return bool(labs & HOLD_LABELS)
