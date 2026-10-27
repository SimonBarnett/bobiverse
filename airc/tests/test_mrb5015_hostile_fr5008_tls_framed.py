"""Hostile pin MRB #5015: FR #5008 reverse-DCC TLS/framed leftovers in airc troubleshooting."""
from __future__ import annotations

from pathlib import Path

import repo_layout

SKILL = (
    repo_layout.ROOT
    / "airc"
    / ".grok"
    / "skills"
    / "bobiverse-airc-troubleshooting"
    / "SKILL.md"
)


def test_fr5008_tls12_and_framed_leftover_phrases_contiguous():
    text = SKILL.read_text(encoding="utf-8")
    assert not text.startswith("\ufeff")
    # Contiguous playbook needles from docs tip #5015 / product #5013.
    assert "## FR #5008 (reverse-DCC TLS + framed leftovers)" in text
    assert "Pin TLS **1.2**" in text
    assert "wrap_socket" in text and "race the client close" in text
    assert "slice the body to the declared length" in text
    assert "keep recv leftovers" in text
    assert "Product tip: PR #5013" in text
    # Prior WP1 row still present (do not clobber).
    assert "## FR #5003 (reverse DCC bulk" in text
    assert "DONE id=... exit=... bytes=N sha256=H via=dcc" in text