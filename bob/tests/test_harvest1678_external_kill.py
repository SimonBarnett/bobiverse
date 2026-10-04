"""Harvest #1678: external-kill create-parent cache + deferred bin delete."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "bob/.grok/skills/bobiverse-bob-worker/SKILL.md"
TROUBLE = ROOT / "bob/.grok/skills/bobiverse-bob-troubleshooting/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def test_harvest1678_worker_external_kill():
    text = WORKER.read_text(encoding="utf-8")
    _no_bom(WORKER)
    assert "1643" in text or "1678" in text
    assert "start_agent" in text
    assert "parent" in text.lower()
    assert "defer" in text.lower() or "exclusive-open" in text


def test_harvest1678_troubleshooting_and_log():
    t = TROUBLE.read_text(encoding="utf-8")
    log = LOG.read_text(encoding="utf-8")
    _no_bom(TROUBLE)
    _no_bom(LOG)
    assert "1678" in t and "1643" in t
    assert "#1678" in log