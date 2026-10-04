"""Harvest #1632: bob MRB/UAT vision-first uses bob/VISION.md."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MRB = ROOT / "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md"
UAT = ROOT / "bob/.grok/skills/bobiverse-bob-job-uat/SKILL.md"
BOB = ROOT / "bob/.grok/skills/bobiverse-bob/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"
VISION = ROOT / "bob/VISION.md"
PATHS = (MRB, UAT, BOB, LOG, VISION, Path(__file__))


def _utf8_no_bom(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert raw.endswith(b"\n"), path
    text = raw.decode("utf-8")
    assert "\n<<<<<<<" not in text and not text.startswith("<<<<<<<")
    return text


def test_harvest1632_bob_vision_file_exists():
    assert VISION.is_file()
    _utf8_no_bom(VISION)


def test_harvest1632_job_skills_point_at_bob_vision():
    mrb = _utf8_no_bom(MRB)
    uat = _utf8_no_bom(UAT)
    bob = _utf8_no_bom(BOB)
    assert "bob/VISION.md" in mrb
    assert "1632" in mrb or "1615" in mrb
    assert "bob/VISION.md" in uat
    assert "VISION.md" in bob
    assert "common/docs/vision.md" in mrb or "umbrella" in mrb.lower()


def test_harvest1632_log():
    text = _utf8_no_bom(LOG)
    assert "#1632" in text
    assert "bob/VISION.md" in text
    assert "bob product vision path" in text


def test_harvest1632_files_end_with_newline():
    for p in PATHS:
        assert p.read_bytes().endswith(b"\n"), p
