# -*- coding: utf-8 -*-
"""FR #9669: CAST IRON needs-walrus NACK → Jeeves agent; split code + walrus FRs.

Pins the rule in monitor, fr-filing, job-irc, job-fr, AGENTS, and harvest.
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import REPO

JEEVES = REPO / "jeeves"
AGENTS = JEEVES / "AGENTS.md"
MONITOR = JEEVES / ".grok" / "skills" / "bobiverse-jeeves-monitor" / "SKILL.md"
FR_FILING = JEEVES / ".grok" / "skills" / "bobiverse-jeeves-agent-fr-filing" / "SKILL.md"
JOB_IRC = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-job-irc" / "SKILL.md"
JOB_FR = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"
HARVEST = REPO / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"

NEEDLES = (
    "9669",
    "needs-walrus",
    "Jeeves agent",
)


def _assert_book(path: Path) -> str:
    assert path.is_file(), path
    text = path.read_text(encoding="utf-8-sig")
    for needle in NEEDLES:
        assert needle in text, f"{needle!r} missing from {path}"
    low = text.lower()
    assert "split" in low or "digest" in low, path
    assert "require_machine" in low or "walrus action" in low, path
    return text


def test_fr9669_monitor_cast_iron_point():
    text = _assert_book(MONITOR)
    assert "CAST IRON" in text
    assert "ACK" in text and "GIVEUP" in text
    assert "Slab" in text or "Si-yes" in text or "SiYes" in text


def test_fr9669_fr_filing_split_section():
    text = _assert_book(FR_FILING)
    assert "Code" in text
    assert "Walrus action" in text or "walrus action" in text.lower()
    assert "Depends-on" in text


def test_fr9669_job_irc_and_fr_hand_off():
    _assert_book(JOB_IRC)
    _assert_book(JOB_FR)


def test_fr9669_agents_and_harvest():
    _assert_book(AGENTS)
    text = _assert_book(HARVEST)
    assert "9652" in text or "Digest" in text
