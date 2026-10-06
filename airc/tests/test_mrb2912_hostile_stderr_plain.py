"""Hostile pins for MRB #2912 / FR #2910 plain-text PowerShell StdErr.

Product on main via #2912. Pins skill/docs phrases + decoder entry points.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc" / "SKILL.md"
TROUBLE = ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-troubleshooting" / "SKILL.md"
DOCS = ROOT / "airc" / "docs" / "airc-remote-control.md"
CONSOLE = ROOT / "airc" / "scripts" / "airc_console.py"


def test_mrb2912_skill_docs_pin_fr2910():
    for path in (SKILL, TROUBLE, DOCS):
        text = path.read_text(encoding="utf-8")
        assert text.endswith("\n"), path.name
        assert not text.startswith("\ufeff"), path.name
        assert "2910" in text, path.name
        assert "CLIXML" in text, path.name
    skill = SKILL.read_text(encoding="utf-8")
    assert "plain text" in skill.lower()
    assert "FR #2910" in skill
    assert "decoded to plain text by FR #2910" in skill
    trouble = TROUBLE.read_text(encoding="utf-8")
    assert "plain_text_powershell_stderr" in trouble
    assert "_x000D__x000A_" in trouble


def test_mrb2912_code_pins_decoder_and_preamble_newlines():
    src = CONSOLE.read_text(encoding="utf-8")
    assert "def plain_text_powershell_stderr" in src
    assert r'<S\s+S="Error">' in src or 'S="Error"' in src
    assert "_unescape_powershell_clixml_text" in src
    assert "FR #2910" in src
    # Preamble statements newline-separated (not fused with '; ').
    assert "SilentlyContinue'\\n" in src
    assert "UTF8Encoding $false\\n" in src
    assert src.count("plain_text_powershell_stderr(") >= 2
