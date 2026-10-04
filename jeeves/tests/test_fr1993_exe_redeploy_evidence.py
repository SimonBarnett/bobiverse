"""FR #1993: live exe redeploy evidence files stay present and honest."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EV = ROOT / "jeeves" / "docs" / "evidence"
DOC = ROOT / "jeeves" / "docs" / "jeeves-exe-self-heal.md"


def test_redeploy_evidence_md_exists_and_refs_only():
    p = EV / "fr1993-exe-redeploy-2026-10-04.md"
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "Refs" in text
    assert "ircJeeves" in text
    assert "BobIrcd" in text
    assert "7700" in text
    assert "offerable for you" in text or "2335" in text


def test_storm_after_redeploy_summary_ok():
    import json

    p = EV / "fr1993-wp4-storm-after-redeploy.json"
    assert p.is_file()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data.get("ok") is True
    assert data.get("claim_ok") == 50
    assert data.get("done_ok") == 50
    assert data.get("failures") == []
    assert data.get("inproc_lock") is True


def test_self_heal_doc_mentions_redeploy_evidence():
    text = DOC.read_text(encoding="utf-8")
    assert "fr1993-exe-redeploy-2026-10-04.md" in text
