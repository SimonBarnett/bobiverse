"""MRB #2410 hostile: skill-harvest-log C0 / eaten-book gates stay tight."""
from __future__ import annotations

import re

from repo_layout import ROOT

LOG = ROOT / "common" / "docs" / "skill-harvest-log.md"
_CTRL = {chr(i) for i in range(32)} - {"\n", "\r", "\t"}
_EATEN = re.compile(r"(?<![A-Za-z])obiverse-bob")
_BOOKS_LINE = re.compile(r"(?im)^(Books?|Book)\s*:")


def test_mrb2410_log_utf8_no_bom():
    raw = LOG.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "skill-harvest-log.md must be UTF-8 without BOM"
    raw.decode("utf-8")


def test_mrb2410_no_backspace_or_other_c0():
    text = LOG.read_text(encoding="utf-8")
    assert "\x08" not in text
    bad = sorted({hex(ord(c)) for c in text if c in _CTRL})
    assert not bad, f"C0 controls remain: {bad}"


def test_mrb2410_no_eaten_or_double_b_book_names():
    text = LOG.read_text(encoding="utf-8")
    assert _EATEN.search(text) is None
    assert "bbobiverse" not in text
    assert "\x08obiverse" not in text
    # FR #2408 evidence lines must read as full bobiverse-* book ids.
    assert "bobiverse-bob-job-mrb" in text
    assert "bobiverse-bob-worker" in text
    assert "bobiverse-bob-troubleshooting" in text


def test_mrb2410_no_duplicate_consecutive_books_lines():
    """Repair of two damaged Books lines must not leave identical adjacent dupes."""
    lines = LOG.read_text(encoding="utf-8").splitlines()
    prev = None
    for i, line in enumerate(lines):
        if not _BOOKS_LINE.match(line.strip()):
            prev = None
            continue
        norm = " ".join(line.split())
        assert norm != prev, f"duplicate consecutive Books lines at {i + 1}: {norm}"
        prev = norm
