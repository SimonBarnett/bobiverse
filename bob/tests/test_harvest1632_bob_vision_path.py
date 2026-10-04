"""Harvest #1632: bob MRB/UAT vision-first uses bob/VISION.md."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MRB = ROOT / "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md"
UAT = ROOT / "bob/.grok/skills/bobiverse-bob-job-uat/SKILL.md"
BOB = ROOT / "bob/.grok/skills/bobiverse-bob/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"
VISION = ROOT / "bob/VISION.md"


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def test_harvest1632_bob_vision_file_exists():
    assert VISION.is_file()
    _no_bom(VISION)


def test_harvest1632_job_skills_point_at_bob_vision():
    mrb = MRB.read_text(encoding="utf-8")
    uat = UAT.read_text(encoding="utf-8")
    bob = BOB.read_text(encoding="utf-8")
    for path, text in ((MRB, mrb), (UAT, uat), (BOB, bob)):
        _no_bom(path)
    assert "bob/VISION.md" in mrb
    assert "1632" in mrb or "1615" in mrb
    assert "bob/VISION.md" in uat
    assert "VISION.md" in bob
    assert "common/docs/vision.md" in mrb or "umbrella" in mrb.lower()


def test_harvest1632_log():
    text = LOG.read_text(encoding="utf-8")
    _no_bom(LOG)
    assert "#1632" in text
    assert "bob/VISION.md" in text