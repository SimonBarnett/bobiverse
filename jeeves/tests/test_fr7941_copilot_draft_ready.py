"""FR #7941: finished Copilot drafts are marked ready once and queued as MRB."""
from __future__ import annotations

import gitclaim
import copilot_draft_ready as cdr

REPO = "SimonBarnett/bobiverse"
NOW = 1_000_000.0


def _pr(**kw):
    base = {
        "repo": REPO,
        "number": 7937,
        "title": "Restore Grok seat rendering",
        "draft": True,
        "author": {"login": "copilot-swe-agent[bot]"},
        "sha": "abc123",
        "pushed_at": NOW - 400,
        "commits": [
            {"message": "Initial plan"},
            {"message": "Keep Grok console stderr inherited"},
        ],
        "checks": [
            {"name": "pytest-ascii-bom", "status": "COMPLETED", "conclusion": "SUCCESS"},
        ],
        "copilot_wip": False,
    }
    base.update(kw)
    return base


def test_finished_copilot_draft_is_marked_and_queued(tmp_path):
    calls = []
    notes = []
    marked = cdr.promote(
        tmp_path,
        [_pr()],
        now=NOW,
        quiet_s=300,
        mark_ready=lambda pr: calls.append(pr["number"]) or True,
        announce=notes.append,
    )
    assert marked == [f"{REPO}#7937"]
    assert calls == [7937]
    assert len(notes) == 1
    rows = gitclaim.load_unaccepted(tmp_path)
    assert any(r.get("task") == "MRB" and r.get("id") == "#7937" for r in rows)
    again = cdr.promote(
        tmp_path,
        [_pr()],
        now=NOW + 1000,
        quiet_s=300,
        mark_ready=lambda pr: calls.append(pr["number"]) or True,
        announce=notes.append,
    )
    assert again == []
    assert calls == [7937]
    assert len(notes) == 1


def test_initial_plan_only_stays_draft():
    reason = cdr.block_reason(
        _pr(commits=[{"message": "Initial plan"}]), NOW, 300
    )
    assert reason == "initial-plan-only"


def test_failing_or_pending_check_stays_draft():
    bad = _pr(checks=[{"name": "pytest", "status": "COMPLETED", "conclusion": "FAILURE"}])
    pending = _pr(checks=[{"name": "pytest", "status": "IN_PROGRESS", "conclusion": ""}])
    assert cdr.block_reason(bad, NOW, 300) == "checks-failed"
    assert cdr.block_reason(pending, NOW, 300) == "checks-pending"


def test_human_draft_is_never_touched(tmp_path):
    calls = []
    marked = cdr.promote(
        tmp_path,
        [_pr(author={"login": "SimonBarnett"})],
        now=NOW,
        quiet_s=300,
        mark_ready=lambda pr: calls.append(pr) or True,
    )
    assert marked == []
    assert calls == []


def test_new_push_resets_the_quiet_period():
    first = _pr(sha="aaa", pushed_at=NOW - 400)
    assert cdr.block_reason(first, NOW, 300) == ""
    pushed = _pr(sha="bbb", pushed_at=NOW - 30)
    assert cdr.block_reason(pushed, NOW, 300) == "quiet-period"


def test_copilot_wip_stays_draft():
    assert cdr.block_reason(_pr(copilot_wip=True), NOW, 300) == "copilot-wip"
