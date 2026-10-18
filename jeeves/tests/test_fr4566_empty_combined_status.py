"""FR #4566: empty combined status must read check-runs; long waits back off."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

mrb_merge_on_green = importlib.import_module("mrb_merge_on_green")

PASS_SHA = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _pass_board(sha: str = PASS_SHA) -> list[dict]:
    return [
        {
            "user": {"login": "flamingo-1"},
            "author_association": "NONE",
            "body": f"## MRB board\n**Verdict:** PASS\nMRB PASS @ {sha}",
            "created_at": "2026-10-17T03:00:00Z",
        }
    ]


def test_empty_pending_status_uses_failed_check_run():
    status = {"state": "pending", "total_count": 0, "statuses": []}
    runs = {
        "check_runs": [
            {"name": "test-and-synth", "status": "completed", "conclusion": "failure"}
        ]
    }
    assert mrb_merge_on_green.combined_status_is_empty(status)
    assert mrb_merge_on_green.checks_from_status_and_runs(status, runs) == "failure:test-and-synth"


def test_empty_pending_status_uses_successful_check_runs():
    status = {"state": "pending", "statuses": []}
    runs = {
        "check_runs": [
            {"name": "classify", "status": "completed", "conclusion": "success"},
            {"name": "test-and-synth", "status": "completed", "conclusion": "success"},
        ]
    }
    assert mrb_merge_on_green.checks_from_status_and_runs(status, runs) == "success"


def test_real_pending_status_is_not_replaced():
    status = {
        "state": "pending",
        "statuses": [{"context": "ci/classic", "state": "pending"}],
    }
    runs = {
        "check_runs": [
            {"name": "test-and-synth", "status": "completed", "conclusion": "failure"}
        ]
    }
    assert not mrb_merge_on_green.combined_status_is_empty(status)
    assert mrb_merge_on_green.checks_from_status_and_runs(status, runs) == "pending"


def test_failed_check_releases_the_row(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    mrb_merge_on_green.enqueue(
        home,
        repo="SimonBarnett/a-search",
        pr="1796",
        pass_sha=PASS_SHA,
        url="https://github.com/SimonBarnett/a-search/pull/1796",
    )
    requeues: list[str] = []
    real = mrb_merge_on_green.requeue_mrb

    def _requeue(home, *, repo, pr, url="", reason=""):
        requeues.append(reason)
        return real(home, repo=repo, pr=pr, url=url, reason=reason)

    mrb_merge_on_green.requeue_mrb = _requeue
    try:
        summary = mrb_merge_on_green.process_pending(
            home,
            fetch_pr=lambda r, p: {
                "repo": r,
                "pr": p,
                "sha": PASS_SHA,
                "merged": False,
                "closed": False,
                "labels": [],
                "title": "waiting",
                "body": "",
                "checks": "failure",
                "html_url": f"https://github.com/{r}/pull/{p}",
            },
            fetch_comments=lambda *_a, **_k: _pass_board(),
            merge_fn=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not merge")),
            now=lambda: 1_000_000.0,
        )
    finally:
        mrb_merge_on_green.requeue_mrb = real
    # FR #4566 follow-up: failed CI leaves the poll list without an MRB re-queue.
    assert summary["requeued"] == 0
    assert summary["ci_failed"] == 1
    assert requeues == []
    led = mrb_merge_on_green.load_ledger(home)
    assert led["pending"] == []
    assert "SimonBarnett/a-search#1796" in led["ci_failed"]


def test_wait_backoff_skips_the_next_fetch(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    mrb_merge_on_green.enqueue(
        home,
        repo="SimonBarnett/a-search",
        pr="3632",
        pass_sha=PASS_SHA,
        url="https://github.com/SimonBarnett/a-search/pull/3632",
    )
    fetches: list[float] = []

    def fetch_pr(repo: str, pr: str) -> dict:
        fetches.append(1)
        return {
            "repo": repo,
            "pr": pr,
            "sha": PASS_SHA,
            "merged": False,
            "closed": False,
            "labels": [],
            "title": "ci",
            "body": "",
            "checks": "pending",
            "html_url": f"https://github.com/{repo}/pull/{pr}",
        }

    first = mrb_merge_on_green.process_pending(
        home,
        fetch_pr=fetch_pr,
        fetch_comments=lambda *_a, **_k: _pass_board(),
        merge_fn=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not merge")),
        now=lambda: 1_000_000.0,
        backoff_base_s=60,
    )
    assert first["wait"] == 1
    assert len(fetches) == 1
    second = mrb_merge_on_green.process_pending(
        home,
        fetch_pr=fetch_pr,
        fetch_comments=lambda *_a, **_k: _pass_board(),
        merge_fn=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not merge")),
        now=lambda: 1_000_030.0,
        backoff_base_s=60,
    )
    assert second["deferred"] == 1
    assert len(fetches) == 1
    assert len(mrb_merge_on_green.load_ledger(home)["pending"]) == 1


def test_wait_cap_requeues_without_another_fetch(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    mrb_merge_on_green.enqueue(
        home,
        repo="SimonBarnett/a-search",
        pr="3632",
        pass_sha=PASS_SHA,
        url="https://github.com/SimonBarnett/a-search/pull/3632",
    )
    doc = mrb_merge_on_green.load_ledger(home)
    doc["pending"][0]["first_wait_epoch"] = 1_000.0
    doc["pending"][0]["next_fetch_epoch"] = 9_999_999.0
    mrb_merge_on_green.save_ledger(home, doc)
    fetches: list[str] = []
    summary = mrb_merge_on_green.process_pending(
        home,
        fetch_pr=lambda r, p: fetches.append(p) or {},
        fetch_comments=lambda *_a, **_k: _pass_board(),
        merge_fn=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not merge")),
        now=lambda: 1_000.0 + 3600.0,
        max_wait_s=3600,
    )
    assert fetches == []
    assert summary["requeued"] == 1
    assert summary["actions"][0]["detail"] == "wait_cap"
    assert mrb_merge_on_green.load_ledger(home)["pending"] == []
