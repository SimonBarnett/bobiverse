"""Harvest #1715 / MRB #1836: NAK busy workers-map playbook; UTF-8 no mojibake."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MONITOR = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-monitor/SKILL.md"
BOB = ROOT / "bob/.grok/skills/bobiverse-bob/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"

MOJIBAKE_MARKERS = ("â†’", "â€”", "â€“", "â†", "Ã¢")


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def _no_mojibake(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for marker in MOJIBAKE_MARKERS:
        assert marker not in text, f"mojibake {marker!r} in {path}"


def test_harvest1715_monitor_nak_busy_workers_map():
    text = MONITOR.read_text(encoding="utf-8")
    _no_bom(MONITOR)
    _no_mojibake(MONITOR)
    assert "1715" in text
    assert "nak" in text.lower() or "NAK" in text
    assert "workers" in text and "working_on" in text
    assert "clear_orphan" in text or "worker_list" in text
    assert "1714" in text
    assert chr(0x2192) in text


def test_harvest1715_bob_tipform_note():
    text = BOB.read_text(encoding="utf-8")
    _no_bom(BOB)
    _no_mojibake(BOB)
    assert "1715" in text
    assert "1714" in text
    assert "workers" in text
    assert chr(0x2192) in text


def test_harvest1715_log():
    text = LOG.read_text(encoding="utf-8")
    _no_bom(LOG)
    _no_mojibake(LOG)
    assert "#1715" in text
    assert "clear_orphan" in text or "workers" in text
