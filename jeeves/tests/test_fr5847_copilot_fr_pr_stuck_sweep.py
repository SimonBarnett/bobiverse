"""FR #5847: Copilot FR PR links + stuck-sweep must not re-dispatch."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import copilot_dispatch as cd
import gitclaim
import stuck_job_sweep as sweep


REPO = "SimonBarnett/bobiverse"


def _iso(now: float) -> str:
    return datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _queue(home: Path, *, unaccepted=None, accepted=None, done=None) -> None:
    home.mkdir(parents=True, exist_ok=True)
    doc = {
        "unaccepted": list(unaccepted or []),
        "accepted": list(accepted or []),
        "done": list(done or []),
    }
    gitclaim.queue_path(home).write_text(json.dumps(doc), encoding="utf-8")


def _copilot_fr_accepted(now: float, *, issue: str = "#5838") -> dict:
    return {
        "repo": REPO,
        "task": "FR",
        "id": issue,
        "nick": "copilot",
        "accepted_ts": _iso(now - 2000.0),
        "line": f"FR {REPO}{issue}",
        "title": f"FR {issue}",
    }


def test_fr5847_helpers_head_and_body():
    assert gitclaim.copilot_fr_head_issue("copilot/fr-5838-x") == "#5838"
    assert gitclaim.is_copilot_fr_implement_pr(head_ref="copilot/fr-5838-putend")
    assert gitclaim.copilot_fr_pr_covers_issue(
        issue_id="#5838",
        title="fix putend",
        body="Fixes #5838",
        head_ref="copilot/other-branch",
        user_login="app/copilot-swe-agent",
    )
    assert not gitclaim.copilot_fr_pr_covers_issue(
        issue_id="#5838",
        title="unrelated",
        body="Fixes #9999",
        head_ref="feature/x",
        user_login="alice",
    )


def test_fr5847_stuck_sweep_settles_head_match_draft(tmp_path: Path):
    """Accepted copilot FR + draft PR on copilot/fr-N-* → done, MRB queued, no release."""
    home = tmp_path / "digest"
    now = 1_700_000_000.0
    _queue(home, accepted=[_copilot_fr_accepted(now, issue="#5838")])
    open_items = [
        {
            "repo": REPO,
            "kind": "pr",
            "id": "#5842",
            "title": "fix putend silent fail",
            "body": "Implements the issue.",
            "draft": True,
            "head_ref": "copilot/fr-5838-putend-silent-fail-fix",
            "user_login": "app/copilot-swe-agent",
        }
    ]
    report = sweep.run_stuck_sweep(
        home,
        now=now,
        live={"flamingo-1"},
        idle={"flamingo-1"},
        activity={},
        open_items=open_items,
        act=True,
    )
    assert report["actions"]["released"] == 0
    assert int(report["actions"].get("copilot_settled") or 0) == 1
    doc = gitclaim.load_queue(home)
    assert doc["accepted"] == []
    assert any(
        str(r.get("result") or "").upper() == "COPILOT_PR"
        and str(r.get("id")).endswith("5838")
        for r in doc["done"]
    )
    mrb = [
        r
        for r in doc["unaccepted"]
        if str(r.get("task") or "").upper() == "MRB"
        and str(r.get("id")).endswith("5842")
    ]
    assert len(mrb) == 1
    stuck = [s for s in report.get("stuck") or [] if s.get("stuck_reason") == "accepted_holder_gone"]
    assert stuck == []


def test_fr5847_stuck_sweep_settles_body_fixes_only(tmp_path: Path):
    """Link from Fixes #N in body with other branch name."""
    home = tmp_path / "digest"
    now = 1_700_000_000.0
    _queue(home, accepted=[_copilot_fr_accepted(now, issue="#5838")])
    open_items = [
        {
            "repo": REPO,
            "kind": "pr",
            "id": "#5900",
            "title": "alternate branch",
            "body": "Fixes #5838\n\nCopilot finished the FR.",
            "draft": True,
            "head_ref": "copilot/fix-alt-name",
            "user_login": "app/copilot-swe-agent",
        }
    ]
    report = sweep.run_stuck_sweep(
        home,
        now=now,
        live={"flamingo-1"},
        idle={"flamingo-1"},
        activity={},
        open_items=open_items,
        act=True,
    )
    assert report["actions"]["released"] == 0
    assert int(report["actions"].get("copilot_settled") or 0) == 1
    doc = gitclaim.load_queue(home)
    assert any(str(r.get("id")).endswith("5900") for r in doc["unaccepted"])


def test_fr5847_negative_no_pr_still_holder_gone(tmp_path: Path):
    """Copilot FR with no PR after 30 min keeps accepted_holder_gone release."""
    home = tmp_path / "digest"
    now = 1_700_000_000.0
    _queue(home, accepted=[_copilot_fr_accepted(now, issue="#5267")])
    report = sweep.run_stuck_sweep(
        home,
        now=now,
        live={"flamingo-1"},
        idle={"flamingo-1"},
        activity={},
        open_items=[],
        act=True,
    )
    assert report["actions"]["released"] == 1
    doc = gitclaim.load_queue(home)
    assert doc["accepted"] == []
    assert any(str(r.get("id")).endswith("5267") for r in doc["unaccepted"])


def test_fr5847_no_second_copilot_handoff_after_settle(tmp_path: Path, monkeypatch):
    """After settle, tick must not emit another copilot: FR hand-off."""
    home = tmp_path / "digest"
    now = 1_700_000_000.0
    # FR already DONE via COPILOT_PR, and also sitting wrongly in unaccepted.
    done_row = _copilot_fr_accepted(now, issue="#5838")
    done_row["result"] = "COPILOT_PR"
    done_row["url"] = f"https://github.com/{REPO}/pull/5842"
    done_row.pop("nick", None)
    unacc = {
        "repo": REPO,
        "task": "FR",
        "id": "#5838",
        "line": f"FR {REPO}#5838",
        "title": "t",
        "retry": True,
        "note": "stuck-sweep:accepted_holder_gone",
    }
    _queue(home, unaccepted=[unacc], done=[done_row])
    # Mark allowance + high priority so tick would otherwise dispatch.
    (home / cd.ALLOWANCE_NAME).write_text(
        json.dumps(
            {
                "enabled": True,
                "unlimited": True,
                "remaining": 99,
                "percent": 100,
                "fetched_at": now,
            }
        ),
        encoding="utf-8",
    )
    announced: list[str] = []
    monkeypatch.setattr(
        cd,
        "is_high_priority",
        lambda _home, _row: True,
    )
    monkeypatch.setattr(
        cd,
        "dispatch_enabled",
        lambda _home: True,
    )
    monkeypatch.setattr(
        cd,
        "cooldown_active",
        lambda _home, now=None: False,
    )
    monkeypatch.setattr(
        cd,
        "has_allowance",
        lambda _home, now=None: True,
    )
    out = cd.tick(
        home,
        now=now,
        post=lambda *_a, **_k: {"status": "ok", "html_url": "https://example/tasks/1"},
        announce=announced.append,
    )
    assert out.get("dispatched", 0) == 0
    assert not any("copilot:" in str(x).lower() and "fr" in str(x).lower() for x in announced)


def test_fr5847_webhook_draft_copilot_becomes_claim():
    """Draft Copilot FR PR is claimable as MRB (not dropped as draft)."""
    payload = {
        "action": "opened",
        "repository": {"full_name": REPO},
        "pull_request": {
            "number": 5842,
            "title": "fix putend",
            "body": "Fixes #5838",
            "draft": True,
            "user": {"login": "app/copilot-swe-agent"},
            "head": {"ref": "copilot/fr-5838-putend"},
            "labels": [],
        },
    }
    claim = gitclaim.claim_from_payload("pull_request", payload)
    assert claim is not None
    assert claim.task == "MRB"
    assert claim.id in ("#5842", "5842") or str(claim.id).endswith("5842")
    assert "#5838" in (claim.refs or ())
    assert claim.opened_by == "copilot"


def test_fr5847_classify_held_not_stuck_when_pr_present(tmp_path: Path):
    home = tmp_path / "digest"
    now = 1_700_000_000.0
    row = _copilot_fr_accepted(now, issue="#5838")
    open_items = [
        {
            "repo": REPO,
            "kind": "pr",
            "id": "#5842",
            "draft": True,
            "head_ref": "copilot/fr-5838-x",
            "user_login": "app/copilot-swe-agent",
            "title": "t",
            "body": "",
        }
    ]
    info = sweep.classify_queue_row(
        row,
        bucket="accepted",
        now=now,
        live={"flamingo-1"},
        idle=set(),
        activity={},
        open_items=open_items,
    )
    assert info["stuck"] is False
    assert info["state"] == "held"
    assert info["rule"] == "copilot_pr"
