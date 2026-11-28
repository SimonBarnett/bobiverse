"""FR #9344: promote monitor D3 + OpenCode paid pin + airc cross-machine not-op lessons."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

MONITOR = ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-monitor" / "SKILL.md"
WORKER = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
AIRC = ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-commands" / "SKILL.md"
LOG = ROOT / "common" / "docs" / "skill-harvest-log.md"


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def test_fr9344_monitor_d3_before_bob_g1():
    text = MONITOR.read_text(encoding="utf-8")
    _no_bom(MONITOR)
    assert "9344" in text
    assert "BOB-G1" in text
    low = text.lower()
    assert "depends-on" in low
    assert "close the digest" in low or "clear depends-on" in low
    assert "unhold" in low


def test_fr9344_worker_opencode_paid_pin():
    lessons = WORKER.with_name("lessons.md")
    text = lessons.read_text(encoding="utf-8")
    _no_bom(lessons)
    assert "9344" in text
    assert "BOB_OPENCODE_MODEL" in text
    assert "deepseek-v4-pro" in text
    assert "MRB" in text
    low = text.lower()
    assert "free" in low and "opencode" in low


def test_fr9344_airc_cross_machine_not_op():
    text = AIRC.read_text(encoding="utf-8")
    _no_bom(AIRC)
    assert "\u2014" not in text
    assert "9344" in text
    assert "exit=126" in text
    assert "not-op" in text
    assert "bob-<other>" in text or "cross-machine" in text.lower()
    assert "same-machine" in text.lower() or "bob-<machine>" in text


def test_fr9344_harvest_log():
    text = LOG.read_text(encoding="utf-8")
    _no_bom(LOG)
    assert "9344" in text
    assert "bobiverse-jeeves-monitor" in text
    assert "bobiverse-bob-worker" in text
    assert "bobiverse-airc-commands" in text


def test_fr9344_files_end_with_newline():
    for p in (MONITOR, WORKER, AIRC, LOG, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
