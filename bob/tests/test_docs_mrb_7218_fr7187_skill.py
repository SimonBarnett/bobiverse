"""docs/mrb-7218: pin FR #7187 start effort skill text."""
from __future__ import annotations

from repo_layout import ROOT


def test_docs_mrb_7218_fr7187_skill_phrases():
    skill = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    assert "FR #7187" in text
    assert "workerStartEffort" in text or "reasoning-effort" in text
    assert "low" in text.lower()
    assert skill.read_bytes()[:3] != b"\xef\xbb\xbf"
