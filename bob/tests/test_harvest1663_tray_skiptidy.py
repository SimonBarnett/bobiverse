"""Harvest #1663: tray SkipTidy autostart + ACCEPTABLE partial-FR drift."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOB = ROOT / "bob/.grok/skills/bobiverse-bob/SKILL.md"
TROUBLE = ROOT / "bob/.grok/skills/bobiverse-bob-troubleshooting/SKILL.md"
MRB = ROOT / "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def test_harvest1663_bob_skiptidy():
    text = BOB.read_text(encoding="utf-8")
    _no_bom(BOB)
    assert "SkipTidy" in text
    assert "1636" in text or "1663" in text


def test_harvest1663_troubleshooting_and_mrb_drift():
    t = TROUBLE.read_text(encoding="utf-8")
    m = MRB.read_text(encoding="utf-8")
    _no_bom(TROUBLE)
    _no_bom(MRB)
    assert "SkipTidy" in t and "1663" in t
    assert "ACCEPTABLE drift" in m or "ACCEPTABLE" in m
    assert "1663" in m


def test_harvest1663_log():
    text = LOG.read_text(encoding="utf-8")
    _no_bom(LOG)
    assert "#1663" in text
    assert "SkipTidy" in text