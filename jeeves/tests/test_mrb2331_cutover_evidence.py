"""MRB #2331 fix: ionos cutover evidence for living #1993 (sticky product already #2330)."""
from __future__ import annotations
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
EV = ROOT / "jeeves/docs/evidence/fr1993-ionos-cutover-2026-10-04.md"
JS = ROOT / "jeeves/docs/evidence/fr1993-wp4-storm-summary.json"
DOC = ROOT / "jeeves/docs/jeeves-exe-self-heal.md"

def test_mrb2331_evidence_files():
    assert EV.is_file() and JS.is_file()
    text = EV.read_text(encoding="utf-8")
    assert "1993" in text
    assert "127.0.0.1:7700" in text
    assert "BobCallback" in text
    assert "Refs" in text or "living" in text.lower()
    assert "2330" in text  # sticky already landed
    assert not EV.read_bytes().startswith(b"\xef\xbb\xbf")
    data = JS.read_text(encoding="utf-8")
    assert '"ok": true' in data or '"ok":true' in data
    assert "claim_ok" in data

def test_mrb2331_docs_wp4_points_at_evidence():
    text = DOC.read_text(encoding="utf-8")
    assert "fr1993-ionos-cutover-2026-10-04.md" in text
    assert "never `Closes`" in text or "never Closes" in text or "Refs" in text
