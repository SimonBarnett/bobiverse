"""Hostile MRB #2077: keep-seats-busy promote survives rebase keep-both onto main.

Locks FR #1967 CAST IRON phrases, no conflict markers, UTF-8 without BOM, and
that skill-harvest-log keeps both #1967 and parallel main sections (#1757).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MONITOR = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-monitor/SKILL.md"
START = ROOT / "jeeves/.grok/skills/monitor-start/SKILL.md"
CHECK = ROOT / "jeeves/tools/monitor/seats_stuck_doing.py"
LOG = ROOT / "common/docs/skill-harvest-log.md"
MARKERS = (b"<<<<<<<", b"=======", b">>>>>>>")


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def _no_markers(path: Path) -> None:
    data = path.read_bytes()
    for m in MARKERS:
        # Only flag line-leading conflict markers (docs may mention them in prose).
        for line in data.splitlines():
            if line.startswith(m):
                raise AssertionError(f"{path} has conflict marker {m!r}")


def test_mrb2077_monitor_cast_iron_phrases():
    text = MONITOR.read_text(encoding="utf-8")
    _no_bom(MONITOR)
    _no_markers(MONITOR)
    assert "1967" in text
    assert "keep seats busy" in text.lower()
    assert "clear_seat_doing" in text
    assert "force-orphan-busy" in text or "--force-orphan-busy" in text
    low = text.lower()
    assert "report-only" in low or "report only" in low
    assert "accepted" in low


def test_mrb2077_harvest_log_keep_both_1967_and_1757():
    text = LOG.read_text(encoding="utf-8")
    _no_bom(LOG)
    _no_markers(LOG)
    assert "1967" in text
    assert "keep seats busy" in text.lower()
    assert "1712" in text
    assert "1757" in text or "keep-both" in text.lower()
    assert "<<<<<<<" not in text


def test_mrb2077_monitor_start_and_check_aligned():
    start = START.read_text(encoding="utf-8")
    check = CHECK.read_text(encoding="utf-8")
    _no_bom(START)
    _no_bom(CHECK)
    _no_markers(START)
    _no_markers(CHECK)
    for blob in (start, check):
        assert "1967" in blob
        assert "keep seats busy" in blob.lower()
        assert "force-orphan-busy" in blob
