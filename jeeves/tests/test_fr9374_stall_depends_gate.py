"""FR #9374: stall detectors must not treat Depends-on-gated FRs as starved work."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import gitclaim
import stall_detectors as sd
import stuck_job_sweep as sweep


def _old_ts(now: float, age_s: float = 3600.0) -> str:
    return datetime.fromtimestamp(now - age_s, tz=timezone.utc).isoformat()


def _fr(
    *,
    repo: str,
    num: int,
    ts: str,
    title: str = "work",
    body: str = "",
    labels=None,
):
    return {
        "task": "FR",
        "repo": repo,
        "id": f"#{num}",
        "ident": str(num),
        "url": f"https://github.com/{repo}/issues/{num}",
        "title": title,
        "body": body,
        "ts": ts,
        "labels": labels or ["feature-request"],
        "event": "issues",
        "line": "FR",
    }


def test_fr9374_idle_with_work_skips_open_depends():
    """FR whose Depends-on target is still open must not fire idle_with_work."""
    now = 1_700_000_000.0
    # Depend is OPEN on GitHub but not itself "waiting" unaccepted work here —
    # only the gated child sits in unaccepted (class of skills-visionary#190).
    child = _fr(
        repo="SimonBarnett/skills-visionary",
        num=190,
        ts=_old_ts(now, 4000),
        title="blocked child",
        body="**Depends-on:** SimonBarnett/skills-visionary#156\n",
    )
    snap = {
        "now": now,
        "idle": ["flamingo-14096"],
        "unaccepted": [child],
        "accepted": [],
        "idle_with_work_s": 600.0,
        "depends_issue_open": lambda repo, num: str(num) in ("156", "156"),
    }
    assert sd.detect_idle_with_work(snap) == []


def test_fr9374_idle_with_work_resumes_when_depend_closed():
    """Once the dependency is absent from open keys (CLOSED), starve can fire."""
    now = 1_700_000_000.0
    child = _fr(
        repo="SimonBarnett/skills-visionary",
        num=190,
        ts=_old_ts(now, 4000),
        title="unblocked child",
        body="**Depends-on:** SimonBarnett/skills-visionary#156\n",
    )
    # Depend not in unaccepted/accepted => not in open_keys; no issue_open =>
    # row_depends_open_reason returns None (BOB-D4 when checker unset).
    snap = {
        "now": now,
        "idle": ["flamingo-14096"],
        "unaccepted": [child],
        "accepted": [],
        "idle_with_work_s": 600.0,
        "depends_issue_open": lambda repo, num: False,
    }
    found = sd.detect_idle_with_work(snap)
    assert len(found) == 1
    assert found[0]["id"] == sd.IDLE_WITH_WORK_ID
    assert "skills-visionary#190" in found[0]["evidence"]["waiting"][0].lower() or "190" in (
        found[0]["evidence"]["waiting"][0]
    )


def test_fr9374_classify_held_depends_on_open(tmp_path: Path):
    """Stuck sweep marks Depends-on-gated FR held with rule depends_on_open."""
    now = 1_700_000_000.0
    home = tmp_path
    dep = _fr(
        repo="SimonBarnett/bobiverse",
        num=9147,
        ts=_old_ts(now, 10_000),
        title="open depend",
    )
    child = _fr(
        repo="SimonBarnett/skills-visionary",
        num=190,
        ts=_old_ts(now, 10_000),
        title="starved lookalike",
        body=(
            "**Depends-on:** SimonBarnett/bobiverse#9147, "
            "SimonBarnett/skills-visionary#156\n"
        ),
    )
    dep156 = _fr(
        repo="SimonBarnett/skills-visionary",
        num=156,
        ts=_old_ts(now, 10_000),
        title="also open",
    )
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [dep, dep156, child], "accepted": [], "done": []},
    )
    info = sweep.classify_queue_row(
        child,
        bucket="unaccepted",
        now=now,
        live=set(),
        idle={"flamingo-14096"},
        home=home,
    )
    assert info["state"] == "held"
    assert info["rule"] == "depends_on_open"
    assert info.get("stuck") is False
    assert info.get("stuck_reason") != "unaccepted_starved"


def test_fr9374_classify_starves_after_depends_close(tmp_path: Path, monkeypatch):
    """When Depends-on targets are closed, unaccepted_starved can apply again."""
    now = 1_700_000_000.0
    home = tmp_path
    child = _fr(
        repo="SimonBarnett/skills-visionary",
        num=190,
        ts=_old_ts(now, 10_000),
        title="ready after depend close",
        body="**Depends-on:** SimonBarnett/skills-visionary#156\n",
    )
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [child], "accepted": [], "done": []},
    )
    monkeypatch.setattr(
        gitclaim, "depends_issue_open_checker", lambda: (lambda repo, num: False)
    )
    info = sweep.classify_queue_row(
        child,
        bucket="unaccepted",
        now=now,
        live=set(),
        idle={"flamingo-1"},
        home=home,
    )
    assert info.get("stuck") is True
    assert info.get("stuck_reason") == "unaccepted_starved"
    assert info.get("state") == "unaccepted"
    assert info.get("rule") != "depends_on_open"
