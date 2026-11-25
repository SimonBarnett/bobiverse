# -*- coding: utf-8 -*-
"""FR #9854: tip-blocking FIX list on held digest without Depends-on.

Fail-when: tip-priority siblings stamped Depends-on held fr-digest (starves offer).
Held digest + tip FIX without Depends-on must stay stamp=False / offerable path.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "common" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import depends_on
import fr_digest_gate

DOC = ROOT / "jeeves" / "docs" / "fr-digest-vs-hold-vs-depends-on.md"
FR_DIGEST_SKILL = (
    ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-agent-fr-digest" / "SKILL.md"
)
FR_FILING_SKILL = (
    ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-agent-fr-filing" / "SKILL.md"
)
HARVEST = ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"


def _read(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    return raw.decode("utf-8")


def test_fr9854_stamp_helper_skips_tip_priority_while_held():
    assert fr_digest_gate.stamp_digest_depends_on(digest_held=True, tip_priority=True) is False
    assert fr_digest_gate.stamp_digest_depends_on(digest_held=True, tip_priority=False) is True
    assert fr_digest_gate.stamp_digest_depends_on(digest_held=False, tip_priority=True) is True
    assert fr_digest_gate.stamp_digest_depends_on(digest_held=False, tip_priority=False) is True


def test_fr9854_merge_does_not_force_held_digest_on_tip_priority():
    """Filing helper must not auto-merge held digest ref onto tip-priority bodies."""
    body = "## What\nTip build-jeeves red\n"
    digest_ref = [("SimonBarnett/bobiverse", 9830)]
    # Tip-priority while held: leave body without Depends-on digest.
    if not fr_digest_gate.stamp_digest_depends_on(digest_held=True, tip_priority=True):
        new_body, changed = body, False
    else:
        new_body, changed = depends_on.merge_depends_on_body(
            body, digest_ref, repo="SimonBarnett/bobiverse"
        )
    assert changed is False
    assert "Depends-on" not in new_body
    refs = depends_on.parse_depends_on(new_body, repo="SimonBarnett/bobiverse")
    assert ("SimonBarnett/bobiverse", 9830) not in refs


def test_fr9854_docs_and_skills_list_only_convention():
    for path in (DOC, FR_DIGEST_SKILL, FR_FILING_SKILL):
        text = _read(path)
        low = text.lower()
        assert "9854" in text, path.name
        assert "tip-priority" in low or "tip priority" in low, path.name
        assert "list only" in low or "list-only" in low, path.name
        assert "depends-on" in low, path.name


def test_fr9854_harvest_lesson_not_wire_depends_on_tip_fix():
    text = _read(HARVEST)
    # Must not teach "wire Depends-on #9830" as the tip-red FIX rule.
    bad = "wire Depends-on #9830; tip-red FIX"
    assert bad not in text
    assert "9854" in text
    assert "list only" in text.lower() or "list-only" in text.lower()