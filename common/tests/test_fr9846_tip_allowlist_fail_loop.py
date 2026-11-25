"""FR #9846: SKIP_FAILED_LOOP must not starve tip allowlist under soft exhaust."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import copilot_haiku_refill as refill


NOW = datetime(2026, 11, 24, 20, 0, 0, tzinfo=timezone.utc)
TIP_ALLOW = (9840, 9821, 9826, 9827, 9782, 9781)


def _failed_task(
    issue: int,
    *,
    hours_ago: float = 1.0,
    infra: bool = False,
    extra_error: dict | None = None,
) -> dict:
    created = NOW - timedelta(hours=hours_ago)
    err = extra_error
    if infra and err is None:
        err = {"code": "missing_conclusion", "message": "conclusion is not available"}
    prompt = (
        f"You are the bobiverse FR worker (virtual seat nick=copilot).\n"
        f"Job: FR #{issue}\nImplement."
    )
    task: dict = {
        "state": "failed",
        "created_at": created.isoformat().replace("+00:00", "Z"),
        "sessions": [{"prompt": prompt, "model": "claude-haiku-4.5"}],
    }
    if err is not None:
        task["sessions"][0]["error"] = err
        task["error"] = err
    return task


def test_failed_loop_counts_real_fails_in_window():
    tasks = [
        _failed_task(9821, hours_ago=0.5),
        _failed_task(9821, hours_ago=1.0),
        _failed_task(9826, hours_ago=0.2),  # only one -> not skipped
        _failed_task(9781, hours_ago=5.0),  # outside 3h window
        _failed_task(9781, hours_ago=5.5),
    ]
    got = refill.failed_loop_issue_ids(tasks, now=NOW, window_hours=3.0, min_fails=2)
    assert got == {9821}


def test_infra_missing_conclusion_does_not_burn_fail_loop():
    tasks = [
        _failed_task(9821, hours_ago=0.5, infra=True),
        _failed_task(9821, hours_ago=1.0, infra=True),
        _failed_task(9821, hours_ago=1.5, infra=True),
    ]
    got = refill.failed_loop_issue_ids(tasks, now=NOW, exclude_infra=True)
    assert got == set()
    # Fail-when: counting infra would wrongly skip tip kids.
    burned = refill.failed_loop_issue_ids(tasks, now=NOW, exclude_infra=False)
    assert burned == {9821}


def test_tip_allowlist_bypass_when_fail_loop_would_starve_all_open_tips():
    failed = {9821, 9826, 9827, 9782, 9781, 9840, 9999}
    open_tips = [9821, 9826, 9782]  # all blocked by failed
    cleared, reason = refill.apply_tip_allowlist_fail_loop_bypass(
        failed, TIP_ALLOW, open_tips
    )
    assert reason == "tip_allowlist_bypass"
    # Tip allowlist ids cleared; unrelated 9999 remains.
    assert 9999 in cleared
    assert cleared.isdisjoint(set(TIP_ALLOW))
    assert 9821 not in cleared


def test_no_bypass_when_one_tip_fr_still_free():
    failed = {9821, 9826}
    open_tips = [9821, 9826, 9840]  # 9840 still free
    cleared, reason = refill.apply_tip_allowlist_fail_loop_bypass(
        failed, TIP_ALLOW, open_tips
    )
    assert reason is None
    assert cleared == failed


def test_no_bypass_when_tip_allowlist_has_no_open_eligible():
    failed = {9821, 9826}
    cleared, reason = refill.apply_tip_allowlist_fail_loop_bypass(
        failed, TIP_ALLOW, open_eligible_tip_frs=[]
    )
    assert reason == "tip_allowlist_exhausted"
    assert cleared == failed


def test_resolve_soft_exhaust_scenario_keeps_one_cca_slot():
    """Acceptance: soft exhaust + 2 prior fails on every tip FR -> still eligible."""
    tasks = []
    for issue in (9821, 9826, 9827, 9782, 9781, 9840):
        tasks.append(_failed_task(issue, hours_ago=0.5))
        tasks.append(_failed_task(issue, hours_ago=1.2))
    # Plus infra noise that must not dominate.
    tasks.append(_failed_task(9821, hours_ago=0.1, infra=True))

    skip, reason = refill.resolve_failed_skip_for_refill(
        tasks,
        tip_allowlist=TIP_ALLOW,
        open_eligible_tip_frs=list(TIP_ALLOW),
        now=NOW,
    )
    assert reason == "tip_allowlist_bypass"
    # Fail-when: old behaviour left every tip FR in skip (zero CCA for tip path).
    raw = refill.failed_loop_issue_ids(tasks, now=NOW)
    assert set(TIP_ALLOW).issubset(raw)
    assert skip.isdisjoint(set(TIP_ALLOW))


def test_fail_when_all_tips_skipped_without_bypass_helper():
    """Document the starvation mode the bypass removes (MONITORING 2026-11-24)."""
    tasks = []
    for issue in TIP_ALLOW:
        tasks.append(_failed_task(issue, hours_ago=0.5))
        tasks.append(_failed_task(issue, hours_ago=1.0))
    raw = refill.failed_loop_issue_ids(tasks, now=NOW)
    assert set(TIP_ALLOW) == raw
    # Without bypass, Get-NextFr over allowlist would yield nothing tip-shaped.
    open_tips = list(TIP_ALLOW)
    assert all(n in raw for n in open_tips)
