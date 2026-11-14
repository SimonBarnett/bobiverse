"""docs/mrb-7208: pin FR #7181 digest 403 skill text."""
from __future__ import annotations

from repo_layout import ROOT


def test_docs_mrb_7208_fr7181_skill_phrases():
    skill = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    assert "FR #7181" in text
    assert "Bobiverse-bobreport/1.0" in text or "bobreport/1.0" in text
    assert "CF-Ray" in text or "cf-ray" in text.lower()
    assert "unhealthy" in text.lower()
    assert skill.read_bytes()[:3] != b"\xef\xbb\xbf"
