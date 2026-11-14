"""docs/mrb-7210: pin FR #7182 digest-idle offer skill text."""
from __future__ import annotations

from repo_layout import ROOT


def test_docs_mrb_7210_fr7182_monitor_skill():
    skill = ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-monitor" / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    assert "FR #7182" in text
    assert "digest" in text.lower() and "idle" in text.lower()
    assert "skips=" in text or "skips" in text
    assert skill.read_bytes()[:3] != b"\xef\xbb\xbf"
