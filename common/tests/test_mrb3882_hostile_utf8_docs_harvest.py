"""MRB #3882 hostile pin: FR #3880 UTF-8 docs harvest lesson contiguous."""
from pathlib import Path

import repo_layout

REPO = Path(repo_layout.REPO)
SKILL = REPO / "common/.grok/skills/harvest/SKILL.md"
NEEDLE = (
    "Product docs/**/*.md must decode as UTF-8; use repo_layout.REPO not Legacy ROOT "
    "for rglob; lone cp1252 0x97 breaks harvest-log readers"
)


def test_mrb3882_hostile_utf8_docs_lesson_contiguous():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert NEEDLE in text
    assert "repo_layout.REPO" in text
    assert "0x97" in text
    assert "Legacy ROOT" in text
