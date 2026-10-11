"""FR #4167: job-mrb/job-uat vision-first cite airc/VISION.md alongside bob/VISION.md."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MRB = ROOT / "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md"
UAT = ROOT / "bob/.grok/skills/bobiverse-bob-job-uat/SKILL.md"
AIRC_VISION = ROOT / "airc/VISION.md"
PATHS = (MRB, UAT, AIRC_VISION, Path(__file__))


def _utf8_no_bom(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert raw.endswith(b"\n"), path
    text = raw.decode("utf-8")
    assert "\n<<<<<<<" not in text and not text.startswith("<<<<<<<")
    return text


def test_fr4167_airc_vision_exists():
    assert AIRC_VISION.is_file()
    _utf8_no_bom(AIRC_VISION)


def test_fr4167_job_mrb_cites_airc_and_bob_vision():
    mrb = _utf8_no_bom(MRB)
    assert "bob/VISION.md" in mrb
    assert "airc/VISION.md" in mrb
    assert "4158" in mrb
    assert "1615" in mrb or "1632" in mrb
    assert "common/docs/vision.md" in mrb
    assert "for **airc**" in mrb


def test_fr4167_job_uat_cites_airc_and_bob_vision():
    uat = _utf8_no_bom(UAT)
    assert "bob/VISION.md" in uat
    assert "airc/VISION.md" in uat
    assert "4158" in uat
    assert "common/docs/vision.md" in uat or "docs\\vision.md" in uat
    assert "for **airc**" in uat or "airc**" in uat


def test_fr4167_files_end_with_newline():
    for p in PATHS:
        assert p.read_bytes().endswith(b"\n"), p
