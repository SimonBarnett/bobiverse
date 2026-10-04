"""Hostile MRB #2241: twin-DONE harvest skip survives rebase keep-both onto main."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "common/scripts/Invoke-BobiverseHarvest.ps1"
SKILL = ROOT / "common/.grok/skills/harvest/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"
TEST = ROOT / "common/tests/test_fr2237_harvest_skip_twin_done_loop.py"
MARKERS = (b"<<<<<<<", b"=======", b">>>>>>>")


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def _no_line_markers(path: Path) -> None:
    for line in path.read_bytes().splitlines():
        for m in MARKERS:
            if line.startswith(m):
                raise AssertionError(f"{path} marker {m!r}")


def test_mrb2241_script_has_twin_done_skip():
    text = SCRIPT.read_text(encoding="utf-8")
    _no_bom(SCRIPT)
    _no_line_markers(SCRIPT)
    assert "Test-HarvestTwinDoneLoop" in text
    assert "2237" in text
    assert re.search(r"(?i)twin-DONE|Duplicate of", text)


def test_mrb2241_skill_and_log_keep_both():
    skill = SKILL.read_text(encoding="utf-8")
    log = LOG.read_text(encoding="utf-8")
    _no_bom(SKILL)
    _no_bom(LOG)
    _no_line_markers(LOG)
    assert "2237" in skill or "twin" in skill.lower()
    assert "2237" in log
    assert "twin-DONE" in log or "twin-DONE" in skill
    # keep-both: parallel main lessons remain
    assert "1967" in log or "keep seats busy" in log.lower() or "1757" in log


def test_mrb2241_fr_tests_present():
    assert TEST.is_file()
    _no_bom(TEST)
    body = TEST.read_text(encoding="utf-8")
    assert "2237" in body
    assert "Test-HarvestTwinDoneLoop" in body or "twin" in body.lower()
