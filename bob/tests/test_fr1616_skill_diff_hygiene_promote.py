"""Harvest #1616: skill/markdown diff orphan-continuation FAIL playbook."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
MRB = ROOT / "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def test_fr1616_mrb_skill_diff_hygiene():
    raw = MRB.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "orphan continuation" in text
    assert "1616" in text or "1608" in text
    assert "FAIL" in text
    assert "## Skill / markdown diff hygiene (harvest #1616)" in text
    # section bullets are complete (no orphan-only line under Checks)
    assert "Every changed SKILL.md / docs bullet still reads as a complete sentence/item." in text


def test_fr1616_skill_harvest_log():
    text = LOG.read_text(encoding="utf-8")
    assert "1616" in text
    assert "orphan" in text.lower() or "mid-bullet" in text
    assert "<<<<<<" not in text
    assert "bobiverse-bob-job-mrb" in text
    assert re.search(r"(?<![b])obiverse-bob-job", text) is None
    assert "bbobiverse" not in text


def test_fr1616_files_end_with_newline():
    for p in (MRB, LOG, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
