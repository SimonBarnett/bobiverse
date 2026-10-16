"""MRB #4399 hostile pins for airc info() UnicodeEncodeError guard (FR #4397)."""
from __future__ import annotations
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def test_mrb4399_info_contiguous_fr4397_and_replace():
    src = (SCRIPTS / "airc_console_service.py").read_text(encoding="utf-8")
    start = src.index("def info(msg: str)")
    end = src.index("\ndef ", start + 1)
    body = src[start:end]
    assert "FR #4397" in body
    assert "UnicodeEncodeError" in body
    assert 'errors="replace"' in body or "errors='replace'" in body
    assert "sys.stdout" in body


def test_mrb4399_troubleshooting_row_pins_charmap_arrow():
    skill = (
        Path(__file__).resolve().parents[1]
        / ".grok"
        / "skills"
        / "bobiverse-airc-troubleshooting"
        / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "FR #4397" in skill
    assert "UnicodeEncodeError" in skill
    assert "\\u2192" in skill or "\u2192" in skill
