"""Harvest #1605: stale bob-worker.exe leaves TUI waiting for Enter after inject."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "bob/.grok/skills/bobiverse-bob-worker/SKILL.md"
TROUBLE = ROOT / "bob/.grok/skills/bobiverse-bob-troubleshooting/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def test_harvest1605_worker_skill_stale_exe():
    text = WORKER.read_text(encoding="utf-8")
    _no_bom(WORKER)
    assert "relay: injected" in text
    assert "1605" in text
    assert "stale" in text.lower()
    assert "Build-BobWorker" in text
    assert "1601" in text


def test_harvest1605_troubleshooting_row():
    text = TROUBLE.read_text(encoding="utf-8")
    _no_bom(TROUBLE)
    assert "#1605" in text
    assert "relay: injected" in text


def test_harvest1605_log():
    text = LOG.read_text(encoding="utf-8")
    _no_bom(LOG)
    assert "#1605" in text