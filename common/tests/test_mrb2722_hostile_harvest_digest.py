"""MRB #2722 hostile: harvest skill digest + audit table (FR #2705 audit)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARVEST = ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"
AUDIT = ROOT / "common" / "docs" / "harvest-lessons-audit-2026-10-06.md"


def _utf8_no_bom(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert raw.endswith(b"\n"), path
    text = raw.decode("utf-8")
    for ln in text.splitlines():
        assert not ln.startswith("<<<<<<< "), path
        assert not ln.startswith("======= "), path
        assert not ln.startswith(">>>>>>> "), path
    return text


def test_mrb2722_digest_section_present():
    text = _utf8_no_bom(HARVEST)
    assert "## Harvest digest (lessons audit 2026-10-06)" in text
    assert "FR #2705" in text or "audit for FR #2705" in text


def test_mrb2722_legacy_harvest_as_fr_twins():
    text = _utf8_no_bom(HARVEST)
    assert "Legacy harvest-as-FR twins" in text
    idx = text.index("Legacy harvest-as-FR twins")
    window = text[idx : idx + 700]
    assert "DONE with that covering PR URL" in window or "covering PR" in window
    assert "Duplicate of" in window
    assert "lesson(" in window or "FR #2705" in window


def test_mrb2722_skill_and_harvest_rows_as_fr():
    text = _utf8_no_bom(HARVEST)
    assert "Skill and harvest rows offered as FR" in text
    idx = text.index("Skill and harvest rows offered as FR")
    window = text[idx : idx + 600]
    assert "Closes" in window
    assert "FR #2237" in window or "Invoke-BobiverseHarvest" in window


def test_mrb2722_intake_and_flush():
    text = _utf8_no_bom(HARVEST)
    assert "Intake and Flush" in text
    idx = text.index("Intake and Flush")
    window = text[idx : idx + 600]
    assert "UTF-8" in window or "PSObject" in window
    assert "502.3" in window or "Flush" in window
    assert "FR #2705" in window or "Lessons" in window


def test_mrb2722_audit_table_file_exists():
    assert AUDIT.is_file(), AUDIT
    text = _utf8_no_bom(AUDIT)
    assert "Harvest lessons audit" in text or "FR #2705" in text
    assert "| # | lesson |" in text or "target book" in text


def test_mrb2722_harvest_skill_cites_audit_table():
    text = _utf8_no_bom(HARVEST)
    assert "harvest-lessons-audit-2026-10-06.md" in text


def test_mrb2722_keep_both_harvested_lessons_intake():
    """Behind-main keep-both: intake section from main must survive with digest."""
    text = _utf8_no_bom(HARVEST)
    assert "## Harvested lessons (intake)" in text
    assert "bobiverse-bob-job-mrb" in text
    assert "## Harvest digest (lessons audit 2026-10-06)" in text


def test_mrb2722_digest_bullets_complete_lines():
    text = _utf8_no_bom(HARVEST)
    start = text.index("## Harvest digest (lessons audit 2026-10-06)")
    chunk = text[start:]
    bullets = [ln for ln in chunk.splitlines() if ln.startswith("- **")]
    assert len(bullets) >= 3
    for ln in bullets:
        assert ln.rstrip().endswith(")") or "lessons:" in ln or "held" in ln
        assert "orphan" not in ln.lower()
