"""Harvest #1613: open-PR MRB survives resync despite stale mrb_done."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JEEVES = ROOT / "jeeves/.grok/skills/bobiverse-jeeves/SKILL.md"
TROUBLE = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-troubleshooting/SKILL.md"
MRB = ROOT / "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def test_harvest1613_jeeves_resync_open_pr():
    text = JEEVES.read_text(encoding="utf-8")
    _no_bom(JEEVES)
    assert "mrb_done" in text
    assert "pr_exists" in text
    assert "1585" in text or "1613" in text


def test_harvest1613_troubleshooting_and_mrb():
    t = TROUBLE.read_text(encoding="utf-8")
    m = MRB.read_text(encoding="utf-8")
    _no_bom(TROUBLE)
    _no_bom(MRB)
    assert "mrb_done" in t and "1613" in t
    assert "mrb_done" in m and ("1585" in m or "1613" in m)


def test_harvest1613_log():
    text = LOG.read_text(encoding="utf-8")
    _no_bom(LOG)
    assert "#1613" in text