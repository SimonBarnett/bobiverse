"""FR #9411: never offer CLOSED issues or ops-monitor trackers as FR.

Incident: hold cleared on #9376 for MONITORING; issue CLOSED with install PASS;
chair still offered FR to redqueen-6400 (budgeted issue_open never fires on
!bored with BORED_GITHUB_CALL_BUDGET=0; ops-monitor body cues were not skip_fr).
"""
from __future__ import annotations

import bobreport
import gitclaim
import registered_machines


OPS_BODY = (
    "## Status\n"
    "- **Ops install NOT done.**\n\n"
    "## CAST IRON (closing rule)\n"
    "Do **not** `Closes` this issue (or any walrus rebuild/install tracker) while "
    "Depends-on / GateIssues are still **OPEN**.\n\n"
    "## Instructions for Jeeves MONITORING agent (YOU)\n\n"
    "You are the **MONITORING** agent on redqueen.\n\n"
    "### GateIssues (script defaults)\n"
    "- skills-visionary **#155** — **OPEN**\n"
)


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"redqueen", "flamingo"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    digest = bobreport.empty_digest()
    digest["machines"]["redqueen"] = bobreport._empty_machine("redqueen")
    digest["machines"]["redqueen"]["worker_list"] = [
        {
            "nick": "redqueen-6400",
            "state": "idle",
            "kind": "grok",
            "start_model": "grok-4",
            "updated": "2026-11-23T18:00:00Z",
        }
    ]
    bobreport.save_digest(tmp_path, digest)
    return tmp_path


def test_ops_monitor_tracker_skip_fr_even_without_hold():
    why = gitclaim.issue_skip_fr_reason(
        title="After Depends-on: rebuild jeeves on walrus",
        body=OPS_BODY,
        labels=("via-intake", "feature-request"),  # hold cleared
        state="open",
    )
    assert why == "ops_monitor_tracker"


def test_offer_skips_closed_issue_via_unbudgeted_live_check(tmp_path, monkeypatch):
    """!bored must not offer when GitHub says closed even if row state unset."""
    home = _home(tmp_path, monkeypatch)
    row = {
        "repo": "SimonBarnett/bobiverse",
        "task": "FR",
        "id": "#9376",
        "seq": 1,
        "title": "rebuild jeeves on walrus",
        "body": "ordinary product body without monitor cues",
        "labels": ["via-intake", "feature-request"],
        "url": "https://github.com/SimonBarnett/bobiverse/issues/9376",
        "event": "issues",
        "line": "FR SimonBarnett/bobiverse#9376",
        "ts": "2026-11-23T18:00:00Z",
        # state intentionally unset — stamped-closed path already covered by #2340
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )

    def issue_open(repo, num):
        assert repo.endswith("bobiverse")
        assert str(num).lstrip("#") == "9376"
        return False  # CLOSED on GitHub

    st, job = gitclaim.offer_focus_top(
        home,
        "redqueen-6400",
        "#redqueen",
        issue_open=issue_open,
        is_pull=lambda *_a, **_k: False,
        pr_exists=lambda *_a, **_k: False,
    )
    assert st == "empty"
    assert job is None
    doc = gitclaim.load_queue(home)
    assert doc["unaccepted"] == []


def test_offer_skips_ops_monitor_tracker_without_hold(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    row = {
        "repo": "SimonBarnett/bobiverse",
        "task": "FR",
        "id": "#9376",
        "seq": 1,
        "title": "After Depends-on + PlanAgent FRs close: rebuild jeeves",
        "body": OPS_BODY,
        "labels": ["via-intake", "feature-request"],  # hold cleared for MONITORING
        "state": "open",
        "url": "https://github.com/SimonBarnett/bobiverse/issues/9376",
        "event": "issues",
        "line": "FR",
        "ts": "t",
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    st, job = gitclaim.offer_focus_top(
        home,
        "redqueen-6400",
        "#redqueen",
        issue_open=lambda *_a, **_k: True,
        is_pull=lambda *_a, **_k: False,
    )
    assert st == "empty"
    assert job is None


def test_assign_refuses_closed_live_issue(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    row = {
        "repo": "SimonBarnett/bobiverse",
        "task": "FR",
        "id": "#9376",
        "seq": 1,
        "title": "rebuild",
        "body": "ship",
        "labels": ["feature-request"],
        "url": "https://github.com/SimonBarnett/bobiverse/issues/9376",
        "event": "issues",
        "line": "FR",
        "ts": "t",
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    st, reason = gitclaim.assign_row(
        home,
        "redqueen-6400",
        "SimonBarnett/bobiverse",
        "FR",
        "9376",
        issue_open=lambda *_a, **_k: False,
        is_pull=lambda *_a, **_k: False,
    )
    assert st == "refused"
    assert "CLOSED" in str(reason) or "closed" in str(reason).lower()
