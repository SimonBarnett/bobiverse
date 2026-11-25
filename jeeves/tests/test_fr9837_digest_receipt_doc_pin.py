"""FR #9837: Digest receipt procedure pinned in fr-filing + MONITORING entry points."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

FR_FILING = ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-agent-fr-filing" / "SKILL.md"
HARVEST = ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"
MONITOR = ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-monitor" / "SKILL.md"
MONITOR_START = ROOT / "jeeves" / ".grok" / "skills" / "monitor-start" / "SKILL.md"
AGENTS = ROOT / "jeeves" / "AGENTS.md"

POINTER = (
    "read `$r.number` from the reporter object (or `ISSUE_NUMBER=` line); "
    "see fr-filing skill for Digest receipt procedure"
)


def _norm(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr9837_fr_filing_receipt_procedure():
    t = _norm(FR_FILING)
    assert "$r.number" in t
    assert "ISSUE_NUMBER=" in t
    assert "queued" in t.lower() or "queued_local" in t
    assert "action" in t
    assert "commented" in t or "reopened" in t
    assert "9837" in t


def test_fr9837_entry_points_point_at_receipt():
    for path in (HARVEST, MONITOR, MONITOR_START, AGENTS):
        t = _norm(path)
        assert "$r.number" in t, path.name
        assert "ISSUE_NUMBER=" in t, path.name
        assert "fr-filing" in t, path.name
