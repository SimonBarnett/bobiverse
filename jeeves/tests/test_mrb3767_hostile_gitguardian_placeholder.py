"""MRB #3767 hostile: harvest lesson GitGuardian secret-placeholder playbook."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

HARVEST = ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"


def test_mrb3767_hostile_gitguardian_secret_placeholder_contiguous():
    text = HARVEST.read_text(encoding="utf-8")
    # Contiguous playbook from merged #3767 (intake in_d2782910792e4011).
    needle = (
        "GitGuardian Generic Password on test placeholders: "
        "use secret-placeholder-* and squash/force-push the PR tip "
        "so the old FAKE_* string is gone from PR history; "
        "bobiverse docs/mrb pins go under jeeves/tests because docs/ is gitignored"
    )
    assert needle in text
    assert "secret-placeholder-*" in text
    assert "FAKE_*" in text
    assert "jeeves/tests" in text
    assert "docs/ is gitignored" in text


def test_mrb3767_hostile_lesson_line_ascii():
    raw = HARVEST.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    # Pin only the new lesson line is ASCII (whole SKILL.md may keep older non-ASCII).
    line = next(
        ln
        for ln in raw.decode("utf-8").splitlines()
        if "GitGuardian Generic Password on test placeholders" in ln
    )
    assert all(ord(ch) < 128 for ch in line), repr(line)
