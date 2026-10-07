"""MRB #3026 hostile pins: Windows Node 22 npm test glob lesson in harvest."""
from __future__ import annotations

from pathlib import Path


def _skill_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / ".grok"
        / "skills"
        / "harvest"
        / "SKILL.md"
    )


def test_mrb3026_harvested_lessons_has_node_test_glob_bullet():
    raw = _skill_path().read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "## Harvested lessons (intake)" in text
    idx = text.index("## Harvested lessons (intake)")
    nxt = text.find("\n## ", idx + 1)
    section = text[idx:] if nxt < 0 else text[idx:nxt]
    assert "node --test" in section
    assert 'tests/**/*.test.js' in section or "tests/**/*.test.js" in section
    assert "MODULE_NOT_FOUND" in section
    lines = [ln for ln in section.splitlines() if "MODULE_NOT_FOUND" in ln]
    assert lines, "Node npm test glob lesson missing"
    assert lines[0].lstrip().startswith("- "), f"orphan/splice: {lines[0]!r}"
    assert "Windows" in lines[0] and "Node 22" in lines[0]


def test_mrb3026_keeps_prior_intake_bullets():
    text = _skill_path().read_text(encoding="utf-8")
    idx = text.index("## Harvested lessons (intake)")
    nxt = text.find("\n## ", idx + 1)
    section = text[idx:] if nxt < 0 else text[idx:nxt]
    # Prior bullets in the same window must remain
    assert "gitclaim queue lock" in section or "pr_exists" in section
    assert "bobiverse-bob-job-mrb" in section
    assert "MODULE_NOT_FOUND" in section
