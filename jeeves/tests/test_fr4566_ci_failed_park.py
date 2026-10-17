"""FR #4566 follow-up: CI-failed PASS rows leave the poll list but keep the PASS SHA.

Resync's ci-wait skip (FR #4466) must still recognise them, so a failed-CI PR with
auto-merge armed on the PASSed head is not re-queued as an MRB, and no GitHub
calls are spent on it in later sweeps.
"""
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

PASS_SHA = "cccccccccccccccccccccccccccccccccccccccc"
NEW_SHA = "dddddddddddddddddddddddddddddddddddddddd"
REPO = "SimonBarnett/a-search"


def _board() -> list[dict]:
    return [
        {
            "user": {"login": "flamingo-1"},
            "author_association": "NONE",
            "body": f"## MRB board\n**Verdict:** PASS\nMRB PASS @ {PASS_SHA}",
            "created_at": "2026-10-17T03:00:00Z",
        }
    ]


def _pr(checks: str):
    def fetch(repo: str, pr: str) -> dict:
        fetch.calls += 1
        return {
            "repo": repo,
            "pr": pr,
            "sha": PASS_SHA,
            "merged": False,
            "closed": False,
            "labels": [],
            "title": "fix",
            "body": "",
            "checks": checks,
            "html_url": f"https://github.com/{repo}/pull/{pr}",
        }

    fetch.calls = 0
    return fetch


def _no_merge(*_a, **_k):
    raise AssertionError("must not merge")


def _enqueue(home: Path, pr: str = "1796") -> None:
    mrb_merge_on_green.enqueue(
        home, repo=REPO, pr=pr, pass_sha=PASS_SHA, url=f"https://github.com/{REPO}/pull/{pr}"
    )


def test_failed_check_parks_and_logs_without_requeue(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    _enqueue(home)
    logs: list[str] = []
    fetch = _pr("failure")
    summary = mrb_merge_on_green.process_pending(
        home,
        fetch_pr=fetch,
        fetch_comments=lambda *_a, **_k: _board(),
        merge_fn=_no_merge,
        log=logs.append,
        now=lambda: 2_000_000.0,
    )
    assert summary["ci_failed"] == 1 and summary["requeued"] == 0
    led = mrb_merge_on_green.load_ledger(home)
    assert led["pending"] == []
    assert led["ci_failed"][f"{REPO}#1796"]["pass_sha"] == PASS_SHA
    assert any("drop ci-failed" in m and "#1796" in m for m in logs)
    q = gitclaim.load_queue(home)
    assert not any(str(r.get("id")).lstrip("#") == "1796" for r in q.get("unaccepted") or [])


def test_parked_row_is_not_fetched_again(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    _enqueue(home)
    fetch = _pr("failure")
    for t in (2_000_000.0, 2_000_060.0, 2_000_120.0):
        mrb_merge_on_green.process_pending(
            home,
            fetch_pr=fetch,
            fetch_comments=lambda *_a, **_k: _board(),
            merge_fn=_no_merge,
            now=lambda t=t: t,
        )
    assert fetch.calls == 1


def test_resync_still_sees_parked_pass_sha(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    _enqueue(home)
    mrb_merge_on_green.process_pending(
        home,
        fetch_pr=_pr("failure"),
        fetch_comments=lambda *_a, **_k: _board(),
        merge_fn=_no_merge,
        now=lambda: 2_000_000.0,
    )
    sha = gitclaim._merge_on_green_pass_sha(home, REPO, 1796)
    assert sha == PASS_SHA
    pr = {"number": 1796, "auto_merge": {"merge_method": "squash"}, "head": {"sha": PASS_SHA}}
    assert gitclaim.open_pr_mrb_waiting_on_ci(pr, sha)
    # A new push (head moved) is a fresh review: resync must re-queue it.
    pushed = {"number": 1796, "auto_merge": {"merge_method": "squash"}, "head": {"sha": NEW_SHA}}
    assert not gitclaim.open_pr_mrb_waiting_on_ci(pushed, sha)


def test_new_pass_enqueue_clears_parked_record(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    _enqueue(home)
    mrb_merge_on_green.process_pending(
        home,
        fetch_pr=_pr("failure"),
        fetch_comments=lambda *_a, **_k: _board(),
        merge_fn=_no_merge,
        now=lambda: 2_000_000.0,
    )
    mrb_merge_on_green.enqueue(home, repo=REPO, pr="1796", pass_sha=NEW_SHA)
    led = mrb_merge_on_green.load_ledger(home)
    assert f"{REPO}#1796" not in led["ci_failed"]
    assert len(led["pending"]) == 1


def test_parked_records_expire_after_ttl(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    _enqueue(home)
    mrb_merge_on_green.process_pending(
        home,
        fetch_pr=_pr("failure"),
        fetch_comments=lambda *_a, **_k: _board(),
        merge_fn=_no_merge,
        now=lambda: 2_000_000.0,
    )
    later = 2_000_000.0 + mrb_merge_on_green.CI_FAILED_TTL_S + 1
    mrb_merge_on_green.process_pending(
        home, fetch_pr=_pr("failure"), merge_fn=_no_merge, now=lambda: later
    )
    assert mrb_merge_on_green.load_ledger(home)["ci_failed"] == {}


def test_legacy_ledger_without_ci_failed_loads(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    path = mrb_merge_on_green.ledger_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"version": 1, "pending": []}', encoding="utf-8")
    assert mrb_merge_on_green.load_ledger(home)["ci_failed"] == {}
    assert gitclaim._merge_on_green_pass_sha(home, REPO, 1796) == ""
