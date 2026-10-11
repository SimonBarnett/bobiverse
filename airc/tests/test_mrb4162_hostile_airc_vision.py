"""Hostile pins for MRB #4162 / FR #4158 (airc/VISION.md)."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

VISION = ROOT / "airc/VISION.md"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"


def test_mrb4162_vision_success_and_locked_contiguous():
    raw = VISION.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.endswith(b"\n")
    text = raw.decode("utf-8")
    assert "\u2014" not in text
    assert "## Success" in text and "| S1 |" in text and "| S5 |" in text
    assert "wonderland" in text.lower() and "FR #3834" in text
    assert "chanserv-probe timeout -> wonderland" in text
    assert "FR #1552" in text or "AppParameters" in text
    locked = text[text.index("## LOCKED") : text.index("## UNKNOWN")]
    assert "AircConsole" in locked
    assert "harvest" in locked.lower()
    assert "airc/VISION.md" in text or "FR #4158" in text


def test_mrb4162_skill_points_at_vision_no_ctrl():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\x07" not in raw
    text = raw.decode("utf-8")
    assert "FR #4158" in text
    assert "airc/VISION.md" in text
    assert "\x07irc/VISION.md" not in text
