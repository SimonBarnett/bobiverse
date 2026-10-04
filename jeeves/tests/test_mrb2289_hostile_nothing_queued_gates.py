"""MRB #2289 hostile: harvest #2285 nothing-queued gate playbook stays accurate."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MONITOR = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-monitor/SKILL.md"
IRC = ROOT / "bob/.grok/skills/bobiverse-bob-job-irc/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def _no_bom(path: Path) -> None:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert raw.endswith(b"\n"), path


def test_mrb2289_monitor_extends_2243_with_require_machine():
    text = MONITOR.read_text(encoding="utf-8")
    _no_bom(MONITOR)
    assert "2285" in text and "2243" in text
    assert "nothing queued" in text.lower()
    assert "require_machine" in text
    assert "offerable to live" in text.lower() or "offerable-to-live" in text.lower() or "offerable to live seats" in text.lower()
    # CAST IRON keep seats busy — must not teach default clear_seat_doing
    lower = text.lower()
    assert "keep seats busy" in lower or "#1967" in text
    assert "report only" in lower or "monitor reports only" in lower
    # Must not claim outside-focus ungated totals prove chair stuck
    assert "outside-focus" in lower or "outside focus" in lower


def test_mrb2289_job_irc_troubleshooting_cites_gates():
    text = IRC.read_text(encoding="utf-8")
    _no_bom(IRC)
    assert "2285" in text and "2243" in text
    assert "require_machine" in text
    assert "nothing queued" in text.lower()
    # Troubleshooting row must mention focus/machine gate, not only ignore/strict
    assert "offerable" in text.lower() or "unaccepted can be large" in text.lower()


def test_mrb2289_harvest_log_keep_both_2243_and_2285():
    log = LOG.read_text(encoding="utf-8")
    _no_bom(LOG)
    assert "2285" in log
    assert "2243" in log
    assert "nothing queued" in log.lower() or "Hand-out empty" in log
    assert "<<<<<<<" not in log
    assert ">>>>>>>" not in log
