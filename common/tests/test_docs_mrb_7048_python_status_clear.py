"""docs/mrb-7048: hostile pins for FR #7035 note_python_resolved wiring."""
from __future__ import annotations

from pathlib import Path

from repo_layout import REPO

BOBREPORT = REPO / "common" / "scripts" / "bobreport.py"
AGENT = REPO / "common" / "scripts" / "irc_agent.py"
SKILL = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob" / "SKILL.md"


def test_docs_mrb_7048_note_python_resolved_helper_contiguous():
    text = BOBREPORT.read_text(encoding="utf-8")
    assert "def note_python_resolved" in text
    assert "FR #7035" in text
    assert 'tag == "missing"' in text
    i = text.index("def note_python_resolved")
    window = text[i : i + 800]
    assert "sanitize_python_digest_tag" in window
    assert "path.unlink()" in window
    assert "<<<<<<<" not in window


def test_docs_mrb_7048_irc_agent_clears_on_spawn_and_preflight():
    text = AGENT.read_text(encoding="utf-8")
    assert text.count("note_python_resolved") >= 2
    assert "FR #7035" in text


def test_docs_mrb_7048_skill_cites_7035_clear():
    text = SKILL.read_text(encoding="utf-8")
    assert "7035" in text
    assert "note_python_resolved" in text
