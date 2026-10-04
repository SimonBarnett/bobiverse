"""Harvest #2179: Jeeves silent to operator while shop assigns — unverified WHOIS."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TS = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-troubleshooting/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def test_fr2179_troubleshooting_row():
    text = TS.read_text(encoding="utf-8")
    assert "2179" in text
    assert "unverified" in text.lower()
    assert "WHOIS" in text or "whois" in text.lower()
    assert "Restart-Service ircJeeves" in text or "ircJeeves" in text
    assert "BobIrcd" in text
    assert "never" in text.lower()
    assert not TS.read_bytes().startswith(b"\xef\xbb\xbf")
    assert TS.read_bytes().endswith(b"\n")


def test_fr2179_harvest_log():
    log = LOG.read_text(encoding="utf-8")
    assert "2179" in log
    assert "WHOIS" in log or "whois" in log.lower()
    assert "BobIrcd" in log
