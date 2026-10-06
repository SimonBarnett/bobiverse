"""Hostile pins for MRB #2919 / FR #2918 user-relative At line: in StdErr.

Product on main via #2919. Pins skill/docs phrases + adjust helpers.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc" / "SKILL.md"
TROUBLE = ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-troubleshooting" / "SKILL.md"
DOCS = ROOT / "airc" / "docs" / "airc-remote-control.md"
CONSOLE = ROOT / "airc" / "scripts" / "airc_console.py"


def test_mrb2919_skill_docs_pin_fr2918():
    for path in (SKILL, TROUBLE, DOCS):
        text = path.read_text(encoding="utf-8")
        assert text.endswith("\n"), path.name
        assert not text.startswith("\ufeff"), path.name
        assert "2918" in text, path.name
    skill = SKILL.read_text(encoding="utf-8")
    assert "rewrites `At line:N`" in skill or "subtracting the preamble line count" in skill
    trouble = TROUBLE.read_text(encoding="utf-8")
    assert "ps_utf8_preamble_line_count" in trouble
    assert "user line + 3" in trouble or "At line:" in trouble


def test_mrb2919_code_pins_at_line_adjust():
    src = CONSOLE.read_text(encoding="utf-8")
    assert "def ps_utf8_preamble_line_count" in src
    assert "def _adjust_at_line_numbers" in src
    assert "at_line_offset" in src
    assert "FR #2918" in src
    assert "_AT_LINE_RE" in src
