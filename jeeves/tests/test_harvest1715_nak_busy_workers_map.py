"""Harvest #1715: NAK busy from stale machines.workers map after lost DONE."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MONITOR = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-monitor/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def test_harvest1715_monitor_nak_busy_workers_map():
    text = MONITOR.read_text(encoding="utf-8")
    _no_bom(MONITOR)
    assert "1715" in text
    assert "nak" in text.lower() or "NAK" in text
    assert "workers" in text and "working_on" in text
    assert "clear_orphan" in text or "worker_list" in text
    assert "1714" in text


def test_harvest1715_log():
    text = LOG.read_text(encoding="utf-8")
    _no_bom(LOG)
    assert "#1715" in text