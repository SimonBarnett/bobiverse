"""MRB #2731 hostile: Clear denylist + no hand-delete skill pins (FR #2727)."""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "common" / "scripts" / "Clear-BobiverseJobWorktrees.ps1"
FR_SKILL = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"
MRB_SKILL = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"
SEAT_SKILL = (
    REPO / "bob" / "agents" / "worker" / ".grok" / "skills" / "bobiverse-worker-seat" / "SKILL.md"
)


def _utf8_no_bom(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert raw.endswith(b"\n"), path
    text = raw.decode("utf-8")
    for ln in text.splitlines():
        assert not ln.startswith("<<<<<<< "), path
        assert not ln.startswith("======= "), path
        assert not ln.startswith(">>>>>>> "), path
    return text


def _classify_leaf(leaf: str) -> tuple[bool, bool]:
    """Mirror Test-IsOperatorOrNonJobLeaf + Test-IsJobWorktreePath leaf rules (FR #2727)."""
    op = bool(
        re.match(r"(?i)^wt-bob-main($|-)", leaf)
        or re.match(r"(?i)^wt-airc($|-)", leaf)
        or re.match(r"(?i)^wt-main$", leaf)
    )
    if op:
        return True, False
    job = bool(
        re.match(r"(?i)^(bob-wt-|job-)?(fr|mrb|uat|docs-mrb)-\d", leaf)
        or re.match(r"(?i)^(bobiverse-|fr-\d|mrb-|uat-)", leaf)
        or re.match(r"(?i)^(bobiverse-|fr-|mrb-|uat-|docs-mrb-).*-wt$", leaf)
    )
    return False, job


def test_mrb2731_operator_leaves_never_job():
    for leaf in ("wt-bob-main-b3f5057", "wt-airc-2615", "wt-main", "wt-bob-main"):
        op, job = _classify_leaf(leaf)
        assert op is True
        assert job is False


def test_mrb2731_hyphenated_durable_job_names_are_job():
    for leaf in ("bob-wt-fr-2696", "job-fr-2727", "docs-mrb-2717", "bobiverse-fr2727-job-wt"):
        op, job = _classify_leaf(leaf)
        assert op is False
        assert job is True


def test_mrb2731_incident_style_names_not_auto_reclaimed():
    """Incident trees Clear did not own must stay non-job so seats cannot invent deletes."""
    for leaf in ("bob-wt-fr2696", "wt-docs-mrb-2688", "wt-mrb-2692"):
        op, job = _classify_leaf(leaf)
        assert job is False, leaf


def test_mrb2731_script_has_protected_and_denylist():
    text = _utf8_no_bom(SCRIPT)
    assert "Test-IsOperatorOrNonJobLeaf" in text
    assert "Test-WorktreeProtected" in text
    assert ".bobiverse-seat" in text
    assert "skipped_protected" in text
    # Bare -wt$ reclaim removed (would be too broad for operator trees).
    assert not re.search(r"leaf\s+-match\s+'\(\?i\)-wt\$'", text)


def test_mrb2731_skills_forbid_invented_delete_lists():
    for skill in (FR_SKILL, MRB_SKILL, SEAT_SKILL):
        text = _utf8_no_bom(skill)
        assert "2727" in text
        low = text.lower()
        assert "clear-bobiversejobworktrees" in low or "clear-bobiversejobworktrees.ps1" in low
        assert "never" in low
        assert (
            "hand-delete" in low
            or "did not select" in low
            or "remove-item" in low
            or "invent" in low
        )


def test_mrb2731_fr_skill_manual_only_own_tree():
    text = _utf8_no_bom(FR_SKILL)
    assert "only on your own job tree" in text.lower()
    assert "giveup" in text.lower() or "GIVEUP" in text
