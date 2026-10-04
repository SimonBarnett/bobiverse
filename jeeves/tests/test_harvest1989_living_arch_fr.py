"""Harvest #1989: living ionos architecture FR playbook."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JEEVES = ROOT / "jeeves/.grok/skills/bobiverse-jeeves/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def test_harvest1989_jeeves_living_arch():
    text = JEEVES.read_text(encoding="utf-8")
    assert "1989" in text
    assert "1993" in text
    assert "require_machine" in text
    assert "append" in text.lower() or "same FR" in text


def test_harvest1989_skill_harvest_log():
    text = LOG.read_text(encoding="utf-8")
    assert "1989" in text
    assert "1993" in text


def test_harvest1989_files_end_with_newline():
    for p in (JEEVES, LOG, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
