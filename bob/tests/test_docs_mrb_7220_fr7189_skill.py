"""docs/mrb-7220: pin FR #7189 list-agents skill text."""
from __future__ import annotations

import codecs
from pathlib import Path

from repo_layout import ROOT

_THIS = Path(__file__).resolve()


def test_docs_mrb_7220_fr7189_skill_phrases():
    skill = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    assert "FR #7189" in text
    assert "list-agents" in text
    assert "grey" in text.lower() or "gray" in text.lower() or "enabled" in text.lower()
    # FR #7246: compare to the real UTF-8 BOM (EF BB BF), not 12 ASCII chars.
    assert skill.read_bytes()[:3] != codecs.BOM_UTF8


def test_fr7246_bom_pin_is_three_byte_utf8_bom():
    """The skill BOM check must use codecs.BOM_UTF8 (3 bytes), never a doubled-escape ASCII literal."""
    src = _THIS.read_text(encoding="utf-8")
    assert "!= codecs.BOM_UTF8" in src
    assert codecs.BOM_UTF8 == bytes((0xEF, 0xBB, 0xBF))
    assert len(codecs.BOM_UTF8) == 3
