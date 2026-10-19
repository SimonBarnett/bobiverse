"""FR #4630: skip FIX-CI for cancelled-only tips; skip shared suite when main is also red."""
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

SHA = "c" * 40
REPO = "SimonBarnett/a-search"


def test_rollup_cancelled_only_returns_cancelled_not_failure():
    runs = {
        "check_runs": [
            {"name": "test-and-synth", "status": "completed", "conclusion": "cancelled"},
            {"name": "lint", "status": "completed", "conclusion": "success"},
        ]
    }
    assert mrb_merge_on_green.rollup_check_runs(runs) == "cancelled"


def test_rollup_real_failure_still_failure():
    runs = {
        "check_runs": [
            {"name": "test-and-synth", "status": "completed", "conclusion": "failure"},
            {"name": "other", "status": "completed", "conclusion": "cancelled"},
        ]
    }
    state = mrb_merge_on_green.rollup_check_runs(runs)
    assert state.startswith("failure")


def test_rollup_annotates_shared_suite_name():
    runs = {
        "check_runs": [
            {
                "name": "test-and-synth",
                "status": "completed",
                "conclusion": "failure",
            }
        ]
    }
    assert mrb_merge_on_green.rollup_check_runs(runs) == "failure:test-and-synth"


def test_fix_ci_skip_reason_cancelled_only():
    assert mrb_merge_on_green.fix_ci_skip_reason("cancelled") == "cancelled-only"
    assert mrb_merge_on_green.fix_ci_skip_reason("canceled") == "cancelled-only"
    assert mrb_merge_on_green.fix_ci_skip_reason("completed/cancelled") == "cancelled-only"
    assert mrb_merge_on_green.fix_ci_skip_reason("failure") is None


def test_fix_ci_skip_reason_shared_suite_when_main_red():
    assert (
        mrb_merge_on_green.fix_ci_skip_reason(
            "failure:test-and-synth", main_red=True
        )
        == "main-also-red-shared-suite"
    )
    assert (
        mrb_merge_on_green.fix_ci_skip_reason(
            "failure:test-and-synth", main_red=False
        )
        is None
    )
    assert mrb_merge_on_green.fix_ci_skip_reason("failure", main_red=True) is None


def test_enqueue_skips_cancelled_only(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    result = mrb_merge_on_green.enqueue_fix_ci(
        home,
        repo=REPO,
        pr="3305",
        pass_sha=SHA,
        detail="cancelled",
        main_red=False,
        now_epoch=1_000.0,
    )
    assert result == "skipped"
    q = gitclaim.load_queue(home)
    assert not any(
        str(r.get("task") or "").upper() == "FIX"
        for r in (q.get("unaccepted") or [])
        if isinstance(r, dict)
    )


def test_enqueue_skips_test_and_synth_when_main_red(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    main_sha = "e" * 40
    result = mrb_merge_on_green.enqueue_fix_ci(
        home,
        repo=REPO,
        pr="3740",
        pass_sha=SHA,
        detail="failure:test-and-synth",
        main_red=True,
        main_sha=main_sha,
        now_epoch=1_000.0,
    )
    # FR #4857: tip skipped, one main-side FIX queued.
    assert result == "skipped_main_added"
    q = gitclaim.load_queue(home)
    fixes = [
        r
        for r in (q.get("unaccepted") or [])
        if isinstance(r, dict) and str(r.get("task") or "").upper() == "FIX"
    ]
    assert len(fixes) == 1
    assert str(fixes[0].get("id") or "").lstrip("#") == "main"
    assert "3740" not in {str(r.get("id") or "").lstrip("#") for r in fixes}


def test_enqueue_still_offers_real_failure_when_main_green(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    result = mrb_merge_on_green.enqueue_fix_ci(
        home,
        repo=REPO,
        pr="3741",
        pass_sha=SHA,
        detail="failure",
        main_red=False,
        now_epoch=1_000.0,
    )
    assert result == "added"


def test_resync_cancelled_does_not_add_fix(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setattr(
        mrb_merge_on_green, "main_branch_checks_red", lambda *_a, **_k: False
    )
    mrb_merge_on_green.enqueue(
        tmp_path,
        repo=REPO,
        pr="3305",
        pass_sha=SHA,
        url=f"https://github.com/{REPO}/pull/3305",
    )
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [], "done": []},
    )
    pr = {
        "number": 3305,
        "title": "tip",
        "body": f"Closes {REPO}#1",
        "html_url": f"https://github.com/{REPO}/pull/3305",
        "state": "open",
        "draft": False,
        "auto_merge": {"merge_method": "merge"},
        "head": {"sha": SHA},
        "user": {"login": "u"},
        "checks": "cancelled",
    }

    def fetch_json(url: str):
        if "/pulls" in url and "state=closed" not in url:
            return [pr]
        if "/issues" in url:
            return []
        return []

    res = gitclaim.resync_from_github(tmp_path, [REPO], fetch_json=fetch_json)
    assert res.get("ok") is True
    assert int(res.get("added") or 0) == 0
    fixes = [
        r
        for r in gitclaim.load_unaccepted(tmp_path)
        if isinstance(r, dict) and str(r.get("task") or "").upper() == "FIX"
    ]
    assert fixes == []
    out = capsys.readouterr().out
    assert "result=skipped" in out or "cancelled" in out.lower()


def test_open_pr_mrb_checks_failed_still_true_for_cancelled():
    """Cancelled exits ci-wait (no MRB re-queue) but FIX enqueue refuses."""
    assert gitclaim.open_pr_mrb_checks_failed("cancelled") is True
    assert gitclaim.open_pr_mrb_checks_failed("canceled") is True
