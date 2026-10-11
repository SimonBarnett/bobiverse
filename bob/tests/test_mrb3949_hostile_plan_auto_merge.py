"""Hostile MRB #3949: plan repo setup auto-merge + required-ci-3948 (FR #3948).

Pins contiguous playbook phrases in plan-enable-prs / plan-git-from-plan /
plan-create-repo so keep-both folds cannot drop the HOT-PATCH hand-off steps.
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

ENABLE = ROOT / "bob/agents/plan/.grok/skills/plan-enable-prs/SKILL.md"
GITPLAN = ROOT / "bob/agents/plan/.grok/skills/plan-git-from-plan/SKILL.md"
CREATE = ROOT / "bob/agents/plan/.grok/skills/plan-create-repo/SKILL.md"

NEEDLE_SECTION = "## Auto-merge + required CI (bobiverse#3948)"
NEEDLE_ALLOW = "gh api -X PATCH repos/SimonBarnett/<name> -F allow_auto_merge=true"
NEEDLE_RULESET = "required-ci-3948"
NEEDLE_NO_POLL = "They never poll CI"
NEEDLE_NO_CI = "No CI yet"


def _utf8_no_bom(path: Path) -> str:
    raw = path.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf", f"{path} must be UTF-8 without BOM"
    # Plan skill books historically ship CRLF without a final newline; pin content only.
    return raw.decode("utf-8")


def test_mrb3949_plan_enable_prs_auto_merge_section():
    text = _utf8_no_bom(ENABLE)
    assert NEEDLE_SECTION in text
    assert NEEDLE_ALLOW in text
    assert NEEDLE_RULESET in text
    assert NEEDLE_NO_POLL in text
    assert NEEDLE_NO_CI in text
    assert "strict_required_status_checks_policy\":false" in text or (
        '"strict_required_status_checks_policy":false' in text
    )
    assert "integration_id\":15368" in text or '"integration_id":15368' in text
    assert "Do **not** require path-filtered or" in text or "Do not require path-filtered" in text.replace("**", "")
    # admin bypass actor
    assert "RepositoryRole" in text
    assert "bypass_mode" in text


def test_mrb3949_plan_git_from_plan_checklist_order():
    text = _utf8_no_bom(GITPLAN)
    assert NEEDLE_ALLOW in text
    assert NEEDLE_RULESET in text
    # unique step numbers in quick checklist
    assert "# 3 auto-merge" in text
    assert "# 4 Cursor app pages" in text
    # no duplicate bare "# 3 Cursor"
    assert "# 3 Cursor app pages" not in text


def test_mrb3949_plan_create_repo_points_at_auto_merge():
    text = _utf8_no_bom(CREATE)
    assert "allow_auto_merge=true" in text
    assert "required-ci-3948" in text
    assert "bobiverse#3948" in text
