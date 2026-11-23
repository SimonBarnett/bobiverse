# -*- coding: utf-8 -*-
"""FR #8838 / BOB-G2 S1: docs distinguish digest go-gate, hold, Depends-on CLOSED.

Fail-when: no docs distinguishing the three; must cite VIS-G3 + BOB-G1 encoding.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "jeeves" / "docs" / "fr-digest-vs-hold-vs-depends-on.md"
MONITOR = ROOT / "jeeves" / "docs" / "monitoring.md"


def _read(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    return raw.decode("utf-8")


def test_fr8838_doc_distinguishes_three_gates():
    assert DOC.is_file(), "jeeves/docs/fr-digest-vs-hold-vs-depends-on.md missing"
    text = _read(DOC)
    low = text.lower()

    # Three gates named distinctly
    assert "go-gate" in low
    assert "fr-digest" in text
    assert "hold" in low
    assert "depends-on" in low and "closed" in low

    # Sections / markers for each gate
    assert "Digest go-gate" in text
    assert "issues-only" in low
    assert "Depends-on CLOSED" in text

    # VIS-G3 + BOB-G1 encoding
    assert "VIS-G3" in text
    assert "BOB-G1" in text
    assert "bob_g1_skip_held_digest" in text
    assert "depends-held" in text
    assert "ok-fr-digest" in text

    # Unhold releases; close optional
    assert "unhold" in low
    assert "optional" in low


def test_fr8838_monitoring_links_chair_note():
    text = _read(MONITOR)
    assert "fr-digest-vs-hold-vs-depends-on.md" in text
    assert "8838" in text or "BOB-G2" in text
