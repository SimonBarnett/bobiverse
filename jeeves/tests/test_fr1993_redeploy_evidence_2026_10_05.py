"""FR #1993: tip redeploy evidence doc exists (Refs-only living FR)."""
from __future__ import annotations

from repo_layout import ROOT

DOC = ROOT / "jeeves" / "docs" / "evidence" / "fr1993-exe-redeploy-2026-10-05.md"


def test_redeploy_evidence_refs_only_and_no_closes():
    raw = DOC.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = DOC.read_text(encoding="utf-8")
    assert "Refs" in text or "Living FR stays open" in text
    assert "Closes #1993" not in text
    assert "ircJeeves" in text and "only" in text
    assert "BobIrcd" in text and "untouched" in text.lower()
    assert "127.0.0.1:7700" in text
    assert "202" in text
    # Hostile MRB #2485: build/backup/tip identity must be recorded
    assert "Build-Jeeves.ps1" in text
    assert "14a6549" in text
    assert "backup-before-1993-redeploy" in text
