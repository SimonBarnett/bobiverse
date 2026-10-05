"""FR #1993: second tip redeploy evidence (Refs-only)."""
from __future__ import annotations

from repo_layout import ROOT

DOC = ROOT / "jeeves" / "docs" / "evidence" / "fr1993-exe-redeploy-2026-10-05b.md"


def test_redeploy_b_evidence_refs_only():
    raw = DOC.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = DOC.read_text(encoding="utf-8")
    assert "Living FR stays open" in text or "Refs" in text
    assert "Closes #1993" not in text
    assert "2469" in text and "2468" in text
    assert "127.0.0.1:7700" in text
    assert "202" in text
    assert "BobIrcd" in text
