"""FR #9850 / #9867: tip-allowlist DIRTY FIX and CLEAN tip MRB beat new / lesson FRs."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import focus_ignore as fi  # noqa: E402
import tip_offer_prefer as tip  # noqa: E402

MON = ROOT.parent / "jeeves" / "tools" / "monitor"
sys.path.insert(0, str(MON))
import intervene_assign as ia  # noqa: E402


def _row(
    task: str,
    num: int,
    *,
    title: str = "",
    labels: list | None = None,
    mergeable=None,
    merge_state: str = "",
    mergeStateStatus: str = "",
    changed_files: list | None = None,
    harvest_lesson: bool = False,
    repo: str = "SimonBarnett/bobiverse",
) -> dict:
    r: dict = {
        "repo": repo,
        "task": task,
        "id": f"#{num}",
        "title": title or f"{task} #{num}",
        "ts": "2026-11-24T20:00:00Z",
    }
    if labels is not None:
        r["labels"] = labels
    if mergeable is not None:
        r["mergeable"] = mergeable
    if merge_state:
        r["mergeable_state"] = merge_state
    if mergeStateStatus:
        r["mergeStateStatus"] = mergeStateStatus
    if changed_files is not None:
        r["changed_files"] = changed_files
    if harvest_lesson:
        r["harvest_lesson"] = True
        r["labels"] = list(r.get("labels") or []) + ["harvest-lesson"]
        r["title"] = title or f"lesson(harvest): tip #{num}"
    return r


def test_fr9850_dirty_tip_fix_ranks_ahead_of_new_fr(tmp_path):
    """DIRTY tip-allowlist FIX + new FR => FIX offered first (fail-when FR wins)."""
    fi.save_focus(
        tmp_path,
        {
            "v": 1,
            "repos": {"SimonBarnett/bobiverse": {"priority": 1, "label": "high", "ts": "t"}},
            "items": {},
            "item_seq": 0,
            "strict": False,
            "updated": "t",
        },
    )
    dirty_fix = _row(
        "FIX",
        9788,
        labels=["fix-conflict"],
        mergeable="CONFLICTING",
        merge_state="DIRTY",
        changed_files=["jeeves/tools/monitor/x.py", "common/scripts/gitclaim.py"],
        title="FIX conflict (conflicting; 9788@deadbeef)",
    )
    new_fr = _row("FR", 9861, title="lesson(harvest): unrelated", harvest_lesson=True)
    plain_fr = _row("FR", 9900, title="plain product FR")

    assert tip.is_dirty_or_conflicting(dirty_fix)
    assert tip.row_is_tip_allowlisted(dirty_fix)
    assert tip.tip_prefer_rank(dirty_fix) < tip.tip_prefer_rank(plain_fr)
    assert tip.tip_prefer_rank(dirty_fix) < tip.tip_prefer_rank(new_fr)

    ordered = fi.sort_unaccepted_rows(tmp_path, [new_fr, plain_fr, dirty_fix])
    assert [r["id"] for r in ordered[:1]] == ["#9788"], ordered
    # Fail-when: without tip prefer, FR (task order 2) beats FIX (default 3).
    assert tip.tip_prefer_rank(dirty_fix) == tip.RANK_TIP_DIRTY_FIX


def test_fr9850_conflicting_tip_fix_beats_fr_in_intervene_plan():
    dirty_fix = _row(
        "FIX",
        9786,
        labels=["via-intake", "fix-conflict"],
        mergeable="CONFLICTING",
        mergeStateStatus="DIRTY",
        changed_files=["common/scripts/mrb_merge_on_green.py"],
    )
    lesson_fr = _row("FR", 9862, harvest_lesson=True)
    idle = [{"nick": "redqueen-1", "pid": 1, "state": "idle", "machine": "redqueen"}]
    planned = ia.plan_assigns(
        idle,
        [lesson_fr, dirty_fix],
        offerable_fn=lambda row, nick: True,
    )
    assert len(planned) == 1
    assert planned[0]["task"] == "FIX"
    assert planned[0]["id"] == "9786"


def test_fr9867_tip_clean_mrb_beats_lesson_fr(tmp_path):
    """CLEAN tip MRB ranks ahead of harvest-lesson FRs (#9867)."""
    fi.save_focus(
        tmp_path,
        {
            "v": 1,
            "repos": {"SimonBarnett/bobiverse": {"priority": 1, "label": "high", "ts": "t"}},
            "items": {},
            "item_seq": 0,
            "strict": False,
            "updated": "t",
        },
    )
    tip_mrb = _row(
        "MRB",
        9842,
        mergeable=True,
        merge_state="CLEAN",
        changed_files=["jeeves/tools/a.py", "common/scripts/b.py"],
        title="FR #9840 tip CLEAN",
    )
    lesson = _row("FR", 9863, harvest_lesson=True)
    assert tip.tip_prefer_rank(tip_mrb) < tip.tip_prefer_rank(lesson)
    ordered = fi.sort_unaccepted_rows(tmp_path, [lesson, tip_mrb])
    assert ordered[0]["id"] == "#9842"
    assert ordered[0]["task"] == "MRB"


def test_fr9850_allowlist_numbers_env(monkeypatch):
    monkeypatch.setenv("BOB_TIP_ALLOWLIST", "9788,9842")
    assert tip.tip_allowlist_numbers() == (9788, 9842)
    row = _row("FIX", 9788, labels=["fix-conflict"], merge_state="DIRTY")
    assert tip.row_is_tip_allowlisted(row)
    other = _row("FIX", 1111, labels=["fix-conflict"], merge_state="DIRTY")
    # Number not allowlisted and no tip paths -> not tip-allowlisted.
    assert not tip.row_is_tip_allowlisted(other)


def test_fr9850_task_order_fix_before_fr():
    assert fi._TASK_ORDER["FIX"] < fi._TASK_ORDER["FR"]
    assert fi._TASK_ORDER["MRB"] < fi._TASK_ORDER["FIX"]
