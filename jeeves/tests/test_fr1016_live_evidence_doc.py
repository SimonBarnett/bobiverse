"""MRB #1156: FR #1016 live evidence doc must cover acceptance criteria."""
from __future__ import annotations

from pathlib import Path

DOC = Path(__file__).resolve().parents[1] / "docs" / "fr-1016-ionos-live-evidence.md"


def test_evidence_doc_exists_and_is_utf8():
    assert DOC.is_file()
    raw = DOC.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "no UTF-8 BOM"
    text = raw.decode("utf-8")
    assert "FR #1016" in text


def test_evidence_covers_acceptance_rows():
    text = DOC.read_text(encoding="utf-8")
    assert "Live ionos chair" in text or "merged skip" in text.lower()
    assert "per-PR UAT" in text or "No per-PR UAT" in text
    assert "nothing queued" in text.lower()
    assert "relay: injected" in text or "last-from" in text
    assert "6 passed" in text or "pytest" in text.lower()


def test_evidence_notes_child_issues_closed():
    text = DOC.read_text(encoding="utf-8")
    for n in ("#610", "#971", "#978", "#996"):
        assert n in text
