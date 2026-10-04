"""Harvest #1647: MRB behind-main merge + body/docs nits discipline."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MRB = ROOT / "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def test_harvest1647_mrb_behind_main_and_nits():
    text = MRB.read_text(encoding="utf-8")
    _no_bom(MRB)
    assert "1647" in text
    assert "origin/main" in text
    assert "docs/mrb" in text or "docs/mrb-" in text
    assert "Duplicates closed" in text
    assert "body" in text.lower() and "nit" in text.lower()
    assert "Behind-main" in text or "behind-main" in text.lower()


def test_harvest1647_log():
    text = LOG.read_text(encoding="utf-8")
    _no_bom(LOG)
    assert "#1647" in text or "1647" in text
    assert "origin/main" in text or "behind" in text.lower()


def test_harvest1647_files_end_with_newline():
    for p in (MRB, LOG, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
