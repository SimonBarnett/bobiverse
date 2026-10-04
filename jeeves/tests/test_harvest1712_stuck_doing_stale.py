"""Harvest #1712: seats_stuck_doing false busy when accepted empty after DONE."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MONITOR = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-monitor/SKILL.md"
BOB = ROOT / "bob/.grok/skills/bobiverse-bob/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"

MOJIBAKE = ("\u00c3\u00a2", "\u00e2\u2020\u2019", "\u00e2\u20ac\u201d")  # common double-encoding needles


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def _no_mojibake(text: str) -> None:
    # UTF-8 mis-decoded as cp1252/latin1 then re-encoded often yields these sequences
    assert "\ufffd" not in text
    assert "Ã¢" not in text
    assert "â†’" not in text
    assert "â€”" not in text


def test_harvest1712_monitor_false_stuck_doing():
    text = MONITOR.read_text(encoding="utf-8")
    _no_bom(MONITOR)
    _no_mojibake(text)
    assert "1712" in text
    assert "seats_stuck_doing" in text
    assert "working_on" in text
    assert "accepted" in text
    assert "!assign" in text


def test_harvest1712_bob_tipform_note():
    text = BOB.read_text(encoding="utf-8")
    _no_bom(BOB)
    _no_mojibake(text)
    assert "1712" in text
    assert "working_on" in text


def test_harvest1712_log():
    text = LOG.read_text(encoding="utf-8")
    _no_bom(LOG)
    assert "#1712" in text or "1712" in text


def test_harvest1712_files_end_with_newline():
    for p in (MONITOR, BOB, LOG, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
