"""Harvest #1717: never stamp needs-mrb1 CAST IRON."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARVEST = ROOT / "common/.grok/skills/harvest/SKILL.md"
FR = ROOT / "bob/.grok/skills/bobiverse-bob-job-fr/SKILL.md"
MON = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-monitor/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def test_fr1717_harvest_omits_stamp():
    text = HARVEST.read_text(encoding="utf-8")
    assert "1717" in text
    assert "needs-human" in text
    low = text.lower()
    assert "do **not** stamp" in text or "never create" in low or "omit" in low


def test_fr1717_job_fr_cast_iron():
    text = FR.read_text(encoding="utf-8")
    assert "1717" in text or "1526" in text
    assert "needs-human" in text


def test_fr1717_monitor_ban():
    text = MON.read_text(encoding="utf-8")
    assert "needs-mrb1" in text
    assert "1717" in text or "1526" in text or "cast iron" in text.lower()


def test_fr1717_skill_harvest_log():
    text = LOG.read_text(encoding="utf-8")
    assert "1717" in text
    assert "<<<<<<" not in text


def test_fr1717_files_end_with_newline():
    for path in (HARVEST, FR, MON, LOG, Path(__file__)):
        assert path.read_bytes().endswith(b"\n"), path
