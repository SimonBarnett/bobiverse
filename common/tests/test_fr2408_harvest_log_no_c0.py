"""FR #2408: skill-harvest-log.md must not embed C0 controls that eat book names."""
from __future__ import annotations

import re

from repo_layout import ROOT

LOG = ROOT / "common" / "docs" / "skill-harvest-log.md"
_CTRL = {chr(i) for i in range(32)} - {"\n", "\r", "\t"}
_LEADING_OBIVERSE = re.compile(r"(?<![A-Za-z])obiverse-bob")


def test_skill_harvest_log_has_no_c0_controls():
    text = LOG.read_text(encoding="utf-8")
    bad = sorted({hex(ord(c)) for c in text if c in _CTRL})
    assert not bad, f"skill-harvest-log.md has C0 controls: {bad}"


def test_skill_harvest_log_book_names_not_eaten():
    text = LOG.read_text(encoding="utf-8")
    assert _LEADING_OBIVERSE.search(text) is None
    assert "bbobiverse" not in text
    # Known damaged Books lines from FR #2408 evidence must read correctly.
    assert "bobiverse-bob-job-mrb" in text
    assert "bobiverse-bob-worker" in text
    assert "bobiverse-bob-troubleshooting" in text
