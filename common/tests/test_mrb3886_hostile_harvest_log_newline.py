"""MRB #3886 hostile pin: harvest-log real trailing newline lesson contiguous."""
from pathlib import Path

import repo_layout

REPO = Path(repo_layout.REPO)
SKILL = REPO / "common/.grok/skills/harvest/SKILL.md"
LOG = REPO / "common/docs/skill-harvest-log.md"
NEEDLE = (
    "When appending skill-harvest-log entries, write a real trailing newline byte; "
    "a literal backslash-n fails endswith(b'\\n') harvest-log gates on CI"
)


def test_mrb3886_hostile_trailing_newline_lesson_contiguous():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert NEEDLE in text
    assert "real trailing newline byte" in text
    assert "literal backslash-n" in text
    assert "endswith(b'\\n')" in text


def test_mrb3886_hostile_skill_harvest_log_ends_with_newline():
    raw = LOG.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.endswith(b"\n"), "skill-harvest-log.md must end with a real newline byte"
