"""FR #791: skills must warn that gh issue close rejects --body-file; use -c/--comment."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SK = ROOT / ".grok" / "skills"


def _skill(name: str) -> str:
    return (SK / f"bobiverse-bob-job-{name}" / "SKILL.md").read_text(encoding="utf-8-sig")


def _has_issue_close_body_file_pitfall(text: str) -> bool:
    """True when the skill documents that issue close rejects --body-file."""
    # Require issue-close context and an explicit body-file rejection cue nearby.
    return bool(
        re.search(
            r"(?is)gh issue close.{0,240}(?:--body-file).{0,120}"
            r"(?:unknown flag|does not (?:accept|support)|rejects?|not (?:valid|supported|accepted))",
            text,
        )
        or re.search(
            r"(?is)(?:--body-file).{0,120}(?:unknown flag|does not (?:accept|support)|rejects?).{0,120}"
            r"gh issue close",
            text,
        )
    )


def test_fr_skill_warns_issue_close_rejects_body_file():
    t = _skill("fr")
    assert "gh issue close" in t
    assert "--comment" in t or "`-c`" in t or " -c " in t
    assert _has_issue_close_body_file_pitfall(t), "FR skill must warn issue close rejects --body-file"


def test_mrb_skill_warns_issue_close_rejects_body_file():
    t = _skill("mrb")
    assert "gh issue close" in t
    assert "--comment" in t
    assert _has_issue_close_body_file_pitfall(t), "MRB skill must warn issue close rejects --body-file"
