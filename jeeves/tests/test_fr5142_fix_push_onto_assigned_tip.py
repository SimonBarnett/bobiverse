"""FR #5142: FIX seat pushes companion commit onto the assigned MRB tip."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MRB = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"
IRC = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-irc" / "SKILL.md"


def test_job_mrb_skill_pins_fr5142_fix_onto_assigned_tip():
    text = MRB.read_text(encoding="utf-8")
    assert "FR #5142" in text
    idx = text.index("FR #5142")
    chunk = text[idx : idx + 900]
    assert "FIX" in chunk
    assert "companion" in chunk.lower()
    assert "assigned" in chunk.lower() or "HEAD:" in chunk
    assert "duplicate" in chunk.lower()


def test_job_irc_skill_pins_fr5142_fix_onto_assigned_tip():
    text = IRC.read_text(encoding="utf-8")
    assert "FR #5142" in text
    idx = text.index("FR #5142")
    chunk = text[idx : idx + 700]
    assert "FIX" in chunk
    assert "companion" in chunk.lower()
