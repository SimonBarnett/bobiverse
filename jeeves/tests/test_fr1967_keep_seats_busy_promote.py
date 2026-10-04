"""FR #1967: keep seats busy — monitor report-only; no casual clear_seat_doing."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MONITOR = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-monitor/SKILL.md"
START = ROOT / "jeeves/.grok/skills/monitor-start/SKILL.md"
CHECK = ROOT / "jeeves/tools/monitor/seats_stuck_doing.py"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def test_fr1967_monitor_keep_seats_busy_cast_iron():
    text = MONITOR.read_text(encoding="utf-8")
    _no_bom(MONITOR)
    assert "1967" in text
    assert "keep seats busy" in text.lower()
    assert "clear_seat_doing" in text
    assert "report-only" in text.lower() or "report only" in text.lower()
    assert "accepted" in text.lower()
    assert "--force-orphan-busy" in text or "force-orphan-busy" in text


def test_fr1967_monitor_start_report_only():
    text = START.read_text(encoding="utf-8")
    _no_bom(START)
    assert "1967" in text
    assert "keep seats busy" in text.lower()
    assert "report only" in text.lower()
    assert "clear_seat_doing" in text


def test_fr1967_seats_stuck_doing_remediation():
    text = CHECK.read_text(encoding="utf-8")
    _no_bom(CHECK)
    assert "1967" in text
    assert "keep seats busy" in text.lower()
    assert "force-orphan-busy" in text
    assert "report only" in text.lower()


def test_fr1967_harvest_log():
    text = LOG.read_text(encoding="utf-8")
    _no_bom(LOG)
    assert "1967" in text
    assert "keep seats busy" in text.lower()


def test_fr1967_files_end_with_newline():
    for p in (MONITOR, START, CHECK, LOG, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
