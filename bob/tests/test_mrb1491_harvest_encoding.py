"""Hostile MRB #1491: no literal backslash-n EOF junk; no mojibake in harvested skills."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRAY = ROOT / "bob" / "scripts" / "Start-BobTrayInteractive.ps1"
MONITOR = ROOT / "jeeves" / ".grok" / "skills" / "monitor-start" / "SKILL.md"


def test_tray_script_has_no_literal_backslash_n():
    raw = TRAY.read_bytes()
    assert not raw.endswith(b"\\n"), "Start-BobTrayInteractive.ps1 ends with literal \\n"
    text = TRAY.read_text(encoding="utf-8-sig")
    assert "\\n" not in text[-20:]


def test_monitor_start_skill_encoding_clean():
    text = MONITOR.read_text(encoding="utf-8")
    assert "â€" not in text
    assert "\\n" not in text
    assert "CAST IRON" in text
    assert "never acts as chair" in text.lower() or "never act as chair" in text.lower()
