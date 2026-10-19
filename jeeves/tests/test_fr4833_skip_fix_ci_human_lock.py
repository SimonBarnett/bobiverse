"""FR #4833: lock/assert-lock red (Simon label) must not FIX-CI or re-queue MRB."""
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


def test_rollup_lock_only_annotates_failure_lock():
    runs = {
        "check_runs": [
            {"name": "validate", "status": "completed", "conclusion": "success"},
            {"name": "GitGuardian", "status": "completed", "conclusion": "success"},
            {"name": "lock", "status": "completed", "conclusion": "failure"},
        ]
    }
    assert mrb_merge_on_green.rollup_check_runs(runs) == "failure:lock"


def test_rollup_assert_lock_name_annotates():
    runs = {
        "check_runs": [
            {"name": "assert-lock", "status": "completed", "conclusion": "failure"},
        ]
    }
    assert mrb_merge_on_green.rollup_check_runs(runs) == "failure:lock"


def test_rollup_lock_plus_real_failure_stays_failure():
    runs = {
        "check_runs": [
            {"name": "lock", "status": "completed", "conclusion": "failure"},
            {"name": "test-and-synth", "status": "completed", "conclusion": "failure"},
        ]
    }
    state = mrb_merge_on_green.rollup_check_runs(runs)
    assert state == "failure"


def test_fix_ci_skip_reason_human_gated_lock():
    assert (
        mrb_merge_on_green.fix_ci_skip_reason("failure:lock") == "human-gated-lock"
    )
    assert (
        mrb_merge_on_green.fix_ci_skip_reason("failure:assert-lock")
        == "human-gated-lock"
    )
    assert mrb_merge_on_green.fix_ci_skip_reason("failure") is None
    assert (
        mrb_merge_on_green.fix_ci_skip_reason("failure:test-and-synth") is None
    )


def test_decide_merge_on_green_lock_is_skip_hold_not_requeue_ci():
    decision = mrb_merge_on_green.decide_merge_on_green(
        pass_sha=SHA,
        current_sha=SHA,
        checks="failure:lock",
    )
    assert decision == "skip_hold"


def test_enqueue_skips_fix_and_parks_needs_human(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    result = mrb_merge_on_green.enqueue_fix_ci(
        home,
        repo=REPO,
        pr="39",
        pass_sha=SHA,
        detail="failure:lock",
        main_red=False,
        now_epoch=1_000.0,
    )
    assert result == "needs_human"
    q = gitclaim.load_queue(home)
    rows = [
        r
        for r in (q.get("unaccepted") or [])
        if isinstance(r, dict) and str(r.get("id") or "") in ("#39", "39")
    ]
    assert rows, "expected a needs_human queue row for the PR"
    assert any(gitclaim.row_needs_human(r) for r in rows)
    assert not any(
        str(r.get("task") or "").upper() == "FIX" and not gitclaim.row_needs_human(r)
        for r in rows
    )
    body = " ".join(str(r.get("body") or "") + " " + str(r.get("title") or "") for r in rows)
    assert "simon-approved-rule-change" in body.lower()


def test_resync_pass_sha_no_automerge_does_not_requeue_mrb(tmp_path, monkeypatch, capsys):
    """ce-priority class: allow_auto_merge=false, PASS@head, lock red -> no MRB."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setattr(
        mrb_merge_on_green, "main_branch_checks_red", lambda *_a, **_k: False
    )
    mrb_merge_on_green.enqueue(
        tmp_path,
        repo=REPO,
        pr="39",
        pass_sha=SHA,
        url=f"https://github.com/{REPO}/pull/39",
    )
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [], "done": []},
    )
    pr = {
        "number": 39,
        "title": "fr-38 tip",
        "body": f"Closes {REPO}#38",
        "html_url": f"https://github.com/{REPO}/pull/39",
        "state": "open",
        "draft": False,
        # allow_auto_merge=false => no auto_merge object
        "auto_merge": None,
        "head": {"sha": SHA},
        "user": {"login": "u"},
        "checks": "failure:lock",
        "labels": [],
    }

    def fetch_json(url: str):
        if "/pulls" in url and "state=closed" not in url:
            return [pr]
        if "/issues" in url:
            return []
        return []

    res = gitclaim.resync_from_github(tmp_path, [REPO], fetch_json=fetch_json)
    assert res.get("ok") is True
    q = gitclaim.load_queue(tmp_path)
    mrbs = [
        r
        for r in (q.get("unaccepted") or [])
        if isinstance(r, dict)
        and str(r.get("task") or "").upper() == "MRB"
        and not gitclaim.row_needs_human(r)
    ]
    assert mrbs == [], f"must not re-queue offerable MRB at PASSed head: {mrbs}"
    offerable_fixes = [
        r
        for r in (q.get("unaccepted") or [])
        if isinstance(r, dict)
        and str(r.get("task") or "").upper() == "FIX"
        and not gitclaim.row_needs_human(r)
    ]
    assert offerable_fixes == [], f"must not offer FIX-CI for lock-only: {offerable_fixes}"
    out = capsys.readouterr().out.lower()
    assert "mrb" not in out or "pass-sha" in out or "needs_human" in out or "skip" in out


def test_open_pr_mrb_pass_sha_unchanged_without_automerge():
    pr = {"auto_merge": None, "head": {"sha": SHA}}
    assert gitclaim.open_pr_mrb_pass_sha_unchanged(pr, SHA) is True
    assert gitclaim.open_pr_mrb_ci_wait_candidate(pr, SHA) is False
    pr2 = {"auto_merge": {"merge_method": "merge"}, "head": {"sha": SHA}}
    assert gitclaim.open_pr_mrb_pass_sha_unchanged(pr2, SHA) is True
    assert gitclaim.open_pr_mrb_ci_wait_candidate(pr2, SHA) is True
