"""MRB #4548 hostile: title do-not-merge still holds; body lesson prose does not."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common" / "scripts"))
gitclaim = importlib.import_module("gitclaim")


def test_mrb4548_hostile_title_do_not_merge_still_holds():
    reason = gitclaim.pr_hold_reason(
        title="WIP: do not merge until reviewed",
        body="Lessons:\n- do not merge the thinner duplicate.\n",
        labels=(),
    )
    assert reason
    assert "do not merge" in reason.lower()


def test_mrb4548_hostile_pr_hold_text_re_is_title_alias():
    assert gitclaim.PR_HOLD_TEXT_RE is gitclaim.PR_HOLD_TITLE_RE
    assert gitclaim.pr_hold_reason(
        title="lesson(harvest): twin tip",
        body="FAIL-supersede; do not merge the thinner duplicate.",
        labels=("harvest-lesson",),
    ) is None


def test_mrb4551_job_mrb_pins_fr4545_body_stamp():
    skill = (ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md").read_text(encoding="utf-8")
    assert "PR body text matches only a line-anchored On hold: or HOLD: stamp" in skill
    assert "must not skip enqueue" in skill
