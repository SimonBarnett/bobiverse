"""Hostile pins for MRB #2984: MSI SkipCopy / sync-skip-stale lives in fleet-ops.

Intake parked the FR #2982 playbook under harvest; durable home is bobiverse-fleet-ops
(same as FR #2948 — do not park under harvest).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FLEET = ROOT / "common" / ".grok" / "skills" / "bobiverse-fleet-ops" / "SKILL.md"
HARVEST = ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"


def _t(p: Path) -> str:
    assert p.is_file(), p
    text = p.read_text(encoding="utf-8")
    assert text.endswith("\n")
    return text


def test_mrb2984_fleet_ops_pins_skipcopy_and_sync_skip_stale():
    text = _t(FLEET)
    assert "FR #2982" in text
    assert "SkipCopy" in text
    assert "sync-skip-stale-worktree" in text
    assert "MsiProductVersion" in text
    assert "VERSION equality alone is not enough" in text or "VERSION equality alone" in text


def test_mrb2984_harvest_does_not_hold_skipcopy_bullet():
    text = _t(HARVEST)
    assert "sync-skip-stale-worktree" not in text
    assert "when -MsiProductVersion is set, SkipCopy so heat-laid" not in text
