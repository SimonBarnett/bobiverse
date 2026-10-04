"""Harvest #1583: Airc MSI upgrade preserves AppParameters / ConsoleHome identity."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AIRC = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"
TROUBLE = ROOT / "airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def test_harvest1583_airc_skill_appparameters_preserve():
    text = AIRC.read_text(encoding="utf-8")
    _no_bom(AIRC)
    assert "AppParameters" in text
    assert "airc-install.json" in text
    assert "ConsoleHome" in text
    assert "#1583" in text or "#1552" in text


def test_harvest1583_troubleshooting_row():
    text = TROUBLE.read_text(encoding="utf-8")
    _no_bom(TROUBLE)
    assert "AppParameters" in text
    assert "#1583" in text or "#1552" in text


def test_harvest1583_log():
    text = LOG.read_text(encoding="utf-8")
    _no_bom(LOG)
    assert "#1583" in text
    assert "AppParameters" in text