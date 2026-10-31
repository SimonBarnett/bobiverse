"""MRB #5420 hostile pins for FR #5364 CredMan fill-holes docs."""
from __future__ import annotations

from repo_layout import ROOT


def test_mrb5420_docs_and_skill_name_credman():
    doc = (ROOT / "airc" / "docs" / "airc-remote-control.md").read_text(encoding="utf-8")
    skill = (ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-troubleshooting" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "FR #5364" in doc
    assert "PriorityAirc/ExtensionAdmin" in doc
    assert "credman-missing" in doc
    assert "FR #5364" in skill
    assert "PriorityAirc/ExtensionAdmin" in skill
    src = (ROOT / "airc" / "scripts" / "airc_extension.py").read_text(encoding="utf-8")
    assert "machine account first" in src.lower() or "FR #5364" in src
    assert not (ROOT / "airc" / "docs" / "airc-remote-control.md").read_bytes().startswith(b"\xef\xbb\xbf")
    assert not (
        ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-troubleshooting" / "SKILL.md"
    ).read_bytes().startswith(b"\xef\xbb\xbf")
