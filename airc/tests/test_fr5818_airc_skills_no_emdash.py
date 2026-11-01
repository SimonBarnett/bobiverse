"""FR #5818: airc skill books stay ASCII --- (no U+2014 em-dash; FR #3935)."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

SKILLS = ROOT / "airc" / ".grok" / "skills"


def test_fr5818_airc_skill_books_have_no_emdash():
    found = []
    for path in sorted(SKILLS.rglob("SKILL.md")):
        text = path.read_text(encoding="utf-8")
        if "\u2014" in text:
            found.append(str(path.relative_to(ROOT)))
    assert not found, found


def test_fr5818_commands_profile_warn_uses_ascii_dash():
    cmd = (SKILLS / "bobiverse-airc-commands" / "SKILL.md").read_text(encoding="utf-8")
    assert "profile_warn" in cmd
    assert "\u2014" not in cmd
    assert "---" in cmd
