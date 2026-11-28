"""FR #10267: FR job resume with a non-git or empty worktree must reuse the open PR on the head branch."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FR = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"
HEADING = "## Resume a non-git or empty worktree (FR #10267)"
CREATE_HEADING = "## DONE URL - capture `gh pr create` output (FR #108)"


def _text() -> str:
    raw = FR.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), FR
    assert raw.endswith(b"\n"), FR
    return raw.decode("utf-8")


def test_fr10267_resume_section_present():
    assert HEADING in _text()


def test_fr10267_resume_section_precedes_create():
    text = _text()
    idx = text.index(HEADING)
    assert idx < text.index(CREATE_HEADING)


def test_fr10267_resume_checks_git_and_head_branch():
    text = _text()
    idx = text.index(HEADING)
    window = text[idx : text.index(CREATE_HEADING)]
    assert "git status" in window
    assert "gh pr list" in window
    assert "--head" in window
    assert "--state all" in window


def test_fr10267_open_pr_reused_not_duplicated():
    text = _text()
    idx = text.index(HEADING)
    window = text[idx : text.index(CREATE_HEADING)]
    assert "OPEN" in window
    assert "never open a second pr" in window.lower()
    assert "gh pr ready" in window
    assert "DONE" in window


def test_fr10267_references_prior_fix():
    text = _text()
    idx = text.index(HEADING)
    window = text[idx : text.index(CREATE_HEADING)]
    assert "#10241" in window or "#10266" in window
