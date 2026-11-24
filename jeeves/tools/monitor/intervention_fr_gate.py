#!/usr/bin/env python3
"""FR #9627: intervention harvest must cite a product ircJeeves FR.

CAST IRON: every MONITORING / ops keep-queue-moving or heal bridge
(``!assign``, ``!sweep``, ``!cleargiveup``, ``!focus``, ``!ignore``, ``!pin``,
``!recycle``, …) owes a product FR the same turn so ircJeeves performs it
deterministically. FR #8827 is bridge-only.

This module is the checklist / CI gate: a harvest Summary+Lesson that records
an intervention without a linked product FR number fails closed.
"""
from __future__ import annotations

import argparse
import re
import sys

# Keep-queue-moving / heal tokens (chair commands + common bridge prose).
_INTERVENTION_RE = re.compile(
    r"(?i)(?:"
    r"!assign\b|!sweep\b|!cleargiveup\b|!focus\b|!ignore\b|!pin\b|!recycle\b|"
    r"\bkeep[- ]queue[- ]moving\b|"
    r"\bLLM\s+!assign\b|\bmanual\s+!assign\b|"
    r"\bbridge(?:d|ing)?\b.{0,40}\b(?:assign|sweep|cleargiveup|recycle)\b|"
    r"\b(?:assign|sweep|cleargiveup|recycle)\b.{0,40}\bbridge(?:d|ing)?\b"
    r")"
)

# Product FR citation shapes accepted in Summary/Lesson.
_PRODUCT_FR_RE = re.compile(
    r"(?i)(?:"
    r"\bFR\s*#\d+\b|"
    r"\b(?:SimonBarnett/)?bobiverse#\d+\b|"
    r"\bCloses\s+(?:SimonBarnett/bobiverse)?#\d+\b|"
    r"\bproduct\s+FR\s*#\d+\b|"
    r"(?<![A-Za-z0-9_/])#\d{3,}\b"  # bare #N (3+ digits; avoid #1 noise)
    r")"
)


def harvest_records_intervention(summary: str, lesson: str = "") -> bool:
    """True when Summary/Lesson describes a MONITORING keep-queue / heal bridge."""
    blob = f"{summary or ''}\n{lesson or ''}"
    return bool(_INTERVENTION_RE.search(blob))


def harvest_has_linked_product_fr(summary: str, lesson: str = "") -> bool:
    """True when Summary/Lesson cites a product FR number."""
    blob = f"{summary or ''}\n{lesson or ''}"
    return bool(_PRODUCT_FR_RE.search(blob))


def check_intervention_harvest(summary: str, lesson: str = "") -> str | None:
    """Return an error string when an intervention harvest lacks a product FR.

    Returns ``None`` when the harvest is clean (no intervention, or FR cited).
    """
    if not harvest_records_intervention(summary, lesson):
        return None
    if harvest_has_linked_product_fr(summary, lesson):
        return None
    return (
        "FR #9627: intervention harvest must cite a product ircJeeves FR "
        "(e.g. #9628 / FR #9622) the same turn; FR #8827 is bridge-only"
    )


def main(argv: list[str] | None = None) -> int:
    """CLI for harvest / monitor: exit 0 ok, 1 finding (missing FR), 2 usage."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--summary", default="", help="Harvest -Summary text")
    p.add_argument("--lesson", default="", help="Harvest -Lesson text")
    args = p.parse_args(argv)
    err = check_intervention_harvest(args.summary, args.lesson)
    if err:
        print(err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
