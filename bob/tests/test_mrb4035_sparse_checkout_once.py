"""MRB #4035: FR skill warns not to re-run sparse-checkout disable on a full tree."""
from __future__ import annotations

from repo_layout import ROOT

SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"

def test_fr4029_sparse_checkout_once_cast_iron():
    text = SKILL.read_text(encoding="utf-8")
    assert "FR #4029 / MRB #4035" in text
    assert "not** re-run" in text or "Do **not** re-run" in text
    assert "already-full" in text
    assert "sparse-checkout disable" in text
    assert not SKILL.read_bytes().startswith(b"\xef\xbb\xbf")
