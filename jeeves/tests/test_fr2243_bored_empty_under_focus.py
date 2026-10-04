"""FR #2243: hand-out empty under focus — diagnose focus-repo queue, not outside-focus ungated."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MONITOR = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-monitor/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def test_fr2243_monitor_hand_out_empty_under_focus():
    text = MONITOR.read_text(encoding="utf-8")
    _no_bom(MONITOR)
    assert "2243" in text
    low = text.lower()
    assert "hand-out empty under focus" in low or "hand-out empty" in low
    assert "outside-focus" in low or "outside focus" in low
    assert "ungated" in low
    assert "re-enqueue" in low or "reenqueue" in low
    assert "mrb" in low
    assert "accepted" in low
    assert "1967" in text  # keep seats busy cross-link


def test_fr2243_harvest_log():
    text = LOG.read_text(encoding="utf-8")
    _no_bom(LOG)
    assert "2243" in text
    assert "hand-out empty" in text.lower() or "outside-focus" in text.lower()
    assert "<<<<<<<" not in text


def test_fr2243_files_end_with_newline():
    for p in (MONITOR, LOG, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
