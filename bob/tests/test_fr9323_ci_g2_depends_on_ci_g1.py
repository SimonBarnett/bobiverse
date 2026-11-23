# -*- coding: utf-8 -*-
"""FR #9323: docs mirror — CI-G2 #8841 Depends-on CI-G1 #8839 before wire."""
from __future__ import annotations

import re

from repo_layout import ROOT

MIRROR = ROOT / "bob/docs/fr/fr-digest-go-gate/FR-CI-G2-depends-on-CI-G1.md"
CLOSES_CHILD_RE = re.compile(
    r"(?im)^\s*(?:Closes|Fixes|Resolves)\s+(?:SimonBarnett/bobiverse)?#?(?:8841|8839)\b"
)


def test_fr9323_mirror_names_gate_and_architecture():
    raw = MIRROR.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "#9323" in text
    assert "#8841" in text
    assert "#8839" in text
    assert "build-jeeves.yml -> open-children script" in text
    assert "Depends-on" in text
    assert "CI-G1" in text and "CI-G2" in text
    assert "waits for CI-G1" in text or "until" in text.lower()


def test_fr9323_mirror_no_closes_ci_g_cards():
    text = MIRROR.read_text(encoding="utf-8")
    for line in text.splitlines():
        assert not CLOSES_CHILD_RE.match(line), line
    assert "Refs SimonBarnett/bobiverse#8841" in text
    assert "Refs SimonBarnett/bobiverse#8839" in text or "#8839" in text
