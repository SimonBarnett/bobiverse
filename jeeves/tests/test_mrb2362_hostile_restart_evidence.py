"""MRB #2362 hostile: FR #2352 restart-verify evidence presence."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EV = ROOT / "jeeves/docs/evidence/fr2352-restart-verify-2026-10-05.md"
DOC = ROOT / "jeeves/docs/jeeves-exe-self-heal.md"


def test_mrb2362_evidence_file_gates():
    raw = EV.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.endswith(b"\n")
    text = EV.read_text(encoding="utf-8")
    assert "2352" in text
    assert "ircJeeves" in text
    assert "7700" in text
    assert "202" in text
    assert "2342" in text and "2348" in text
    assert "BobIrcd" in text or "Ergo" in text
    assert "Could not" in text or "did not" in text.lower()


def test_mrb2362_self_heal_pointer():
    text = DOC.read_text(encoding="utf-8")
    assert "2352" in text
    assert "fr2352-restart-verify" in text
