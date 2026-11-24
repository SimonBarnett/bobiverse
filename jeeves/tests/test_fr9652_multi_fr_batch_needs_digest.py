"""FR #9652: CAST IRON multi-FR batch needs Digest parent (fr-digest)."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

HARVEST = ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"
MONITOR = ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-monitor" / "SKILL.md"
MONITOR_START = ROOT / "jeeves" / ".grok" / "skills" / "monitor-start" / "SKILL.md"
AGENTS = ROOT / "jeeves" / "AGENTS.md"


def _norm(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr9652_harvest_cast_iron_point():
    t = _norm(HARVEST)
    assert "9652" in t
    assert "multi-FR batch needs Digest parent" in t or "multi-FR batch needs Digest" in t
    assert "fr-digest" in t
    assert "Depends-on: #<digest>" in t or "Depends-on: #" in t
    assert "9552" in t  # last-child close


def test_fr9652_monitor_books_cite_rule():
    for path in (MONITOR, MONITOR_START, AGENTS):
        t = _norm(path)
        assert "9652" in t, path.name
        assert "fr-digest" in t, path.name
        assert "Depends-on" in t, path.name
