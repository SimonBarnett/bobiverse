# -*- coding: utf-8 -*-
"""FR #8813 / BOB-D9: docs mirror for #8754 retarget; stays open; no Closes/HOLD."""
from __future__ import annotations

import re

from repo_layout import ROOT

MIRROR = ROOT / "bob/docs/fr/depends-on-jeeves/FR-D9-retarget-8754.md"
PINNED_SHA = "47649cf4ba886bc49e366cd43b984b5bf9d99cba"
INDEX_NEEDLE = "fr-index-depends-on-jeeves-2026-11-21.md"
D1_D8 = ("#8805", "#8806", "#8807", "#8808", "#8809", "#8810", "#8811", "#8812")
# Line-anchored owner HOLD stamp (gitclaim FR_HOLD_BODY_RE / PR_HOLD_BODY_RE shape).
HOLD_STAMP_RE = re.compile(
    r"(?im)^\s*(?:\*\*)?(?:On\s+hold|HOLD)\b(?:\s*\([^)]*\))?(?:\*\*)?\s*:"
)
CLOSES_8754_RE = re.compile(
    r"(?im)^\s*(?:Closes|Fixes|Resolves)\s+(?:SimonBarnett/bobiverse)?#?8754\b"
)


def test_fr8813_mirror_index_path_pinned_sha_and_d1_d8():
    raw = MIRROR.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert INDEX_NEEDLE in text
    assert PINNED_SHA in text
    for issue in D1_D8:
        assert issue in text, issue
    assert "stays open" in text.lower()
    assert "#8754" in text


def test_fr8813_mirror_no_closes_8754_and_no_hold_stamp():
    text = MIRROR.read_text(encoding="utf-8")
    for line in text.splitlines():
        assert not CLOSES_8754_RE.match(line), line
        assert not HOLD_STAMP_RE.match(line), line
    assert "Refs SimonBarnett/bobiverse#8754" in text
