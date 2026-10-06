"""MRB #2878 hostile pins for FR #2835 harvest rule restore + skill-dba stage drop."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARVEST = ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"
COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"


def test_mrb2878_harvest_restores_four_wiped_blocks_contiguous():
    raw = HARVEST.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "harvest SKILL.md must be UTF-8 without BOM"
    text = raw.decode("utf-8")
    assert (
        "Skill-intake consolidation: when a worker takes an FR from skill intake (label:skill / harvest), "
        "it must close all open issues for that skill book"
    ) in text
    assert (
        "One issue per issue: when MRB (or any worker) finds a twin/duplicate issue, "
        "close the later one and comment a reference to the first; never leave both open; done issues are closed too."
    ) in text
    assert "### Intake must link an existing harvest PR (FR #1812 / harvest #2013)" in text
    assert "linked_existing_pr" in text
    assert "### Living product FR when intake vanishes into harvest-only (harvest #2001)" in text
    assert "canonical living FR" in text


def test_mrb2878_sync_agent_folders_drops_nested_skill_dba_grok():
    src = COMMON.read_text(encoding="utf-8")
    assert "FR #2835" in src
    assert "skill-dba\\.grok" in src
    assert "Remove-Item -LiteralPath $nestedDbaGrok" in src
    assert "nested skill-dba" in src and "foreign skill-book" in src