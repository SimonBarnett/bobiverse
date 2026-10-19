"""Hostile pins for FR #4833 / MRB #4834: human-gated lock must not FIX-CI or re-MRB."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

mrb_merge_on_green = importlib.import_module("mrb_merge_on_green")
gitclaim = importlib.import_module("gitclaim")

SHA = "a656f2ff2671c6ac7a228619243348105c6b6fa1"
REPO = "SimonBarnett/ce-priority"


def test_hostile_non_lock_check_names_stay_failure():
    """clock/deadlock/unlock must not annotate failure:lock or skip FIX."""
    for name in ("clock", "deadlock", "unlock", "block", "Lockfile"):
        runs = {
            "check_runs": [
                {"name": name, "status": "completed", "conclusion": "failure"},
            ]
        }
        assert mrb_merge_on_green.rollup_check_runs(runs) == "failure", name
        assert mrb_merge_on_green.fix_ci_skip_reason(f"failure:{name}") is None, name


def test_hostile_failure_lock_counts_as_checks_failed():
    """Resync FIX path must still see failure:lock as failed (then park needs_human)."""
    assert gitclaim.open_pr_mrb_checks_failed("failure:lock") is True
    assert gitclaim.open_pr_mrb_checks_failed("failure:assert-lock") is True


def test_hostile_park_stamps_existing_offerable_fix(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    claim = gitclaim.GitClaim(
        repo=REPO,
        task="FIX",
        id="#39",
        event="pull_request",
        action="synchronize",
        line=f"https://github.com/{REPO}/pull/39",
        title="FIX-CI tip red",
        body="offerable fix",
        labels=("via-intake", "fix-ci"),
    )
    qdoc = gitclaim._empty_queue()
    gitclaim._append_unaccepted(
        qdoc,
        claim,
        url=f"https://github.com/{REPO}/pull/39",
        body="offerable fix",
        title="FIX-CI tip red",
        pass_sha=SHA,
    )
    gitclaim._write_queue(gitclaim.queue_path(home), qdoc)
    before = gitclaim.load_queue(home)
    assert any(
        isinstance(r, dict)
        and str(r.get("task") or "").upper() == "FIX"
        and not gitclaim.row_needs_human(r)
        for r in (before.get("unaccepted") or [])
    )
    result = mrb_merge_on_green.park_human_gated_lock(
        home,
        repo=REPO,
        pr="39",
        sha=SHA,
        url=f"https://github.com/{REPO}/pull/39",
        detail="failure:lock",
    )
    assert result == "needs_human"
    q = gitclaim.load_queue(home)
    rows = [
        r
        for r in (q.get("unaccepted") or [])
        if isinstance(r, dict) and str(r.get("id") or "").lstrip("#") == "39"
    ]
    assert rows
    assert all(gitclaim.row_needs_human(r) for r in rows)
    assert not any(
        str(r.get("task") or "").upper() == "FIX" and not gitclaim.row_needs_human(r)
        for r in rows
    )


def test_hostile_evaluate_pending_lock_surfaces_label_reason():
    decision, reason = mrb_merge_on_green.evaluate_pending_row(
        {"pass_sha": SHA},
        pr_state={
            "sha": SHA,
            "checks": "failure:lock",
            "title": "t",
            "body": "",
            "labels": [],
        },
        comments=[],
    )
    assert decision == "skip_hold"
    assert "simon-approved-rule-change" in reason.lower()
