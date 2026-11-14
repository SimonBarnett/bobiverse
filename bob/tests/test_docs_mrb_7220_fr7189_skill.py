"""docs/mrb-7220: pin FR #7189 list-agents skill text."""
from __future__ import annotations

from repo_layout import ROOT


def test_docs_mrb_7220_fr7189_skill_phrases():
    skill = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    assert "FR #7189" in text
    assert "list-agents" in text
    assert "grey" in text.lower() or "gray" in text.lower() or "enabled" in text.lower()
    assert skill.read_bytes()[:3] != b"\\xef\\xbb\\xbf"
