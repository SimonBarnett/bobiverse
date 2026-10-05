"""Harvest #1583: Airc MSI upgrade preserves AppParameters / ConsoleHome identity."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AIRC = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"
TROUBLE = ROOT / "airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def test_harvest1583_airc_skill_appparameters_preserve():
    raw = AIRC.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "AppParameters" in text
    assert "airc-install.json" in text
    assert "ConsoleHome" in text
    assert "1583" in text or "1552" in text


def test_harvest1583_troubleshooting_row():
    raw = TROUBLE.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "AppParameters" in text
    assert "1583" in text or "1552" in text


def test_harvest1583_log():
    raw = LOG.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "harvest #1583" in text
    assert "AppParameters" in text
    assert "airc-install.json" in text
    assert "<<<<<<" not in text


def test_harvest1583_files_end_with_newline():
    for p in (AIRC, TROUBLE, LOG, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
