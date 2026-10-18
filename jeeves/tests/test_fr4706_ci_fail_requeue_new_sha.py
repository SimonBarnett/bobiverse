"""FR #4706: CI fail again after a fix push re-queues FIX for the new head SHA.

Without !resync: parked ci_failed tips whose head advances and fails again must
offer a new FIX. The same SHA failure stays deduped.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

gitclaim = importlib.import_module("gitclaim")
mrb_merge_on_green = importlib.import_module("mrb_merge_on_green")

REPO = "SimonBarnett/a-search"
SHA1 = "a" * 40
SHA2 = "b" * 40


def _home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    return home


def _finish_fix(home: Path, nick: str = "flamingo-30252") -> None:
    q = gitclaim.load_queue(home)
    done = list(q.get("done") or [])
    for row in list(q.get("unaccepted") or []) + list(q.get("accepted") or []):
        if str(row.get("task") or "").upper() != "FIX":
            continue
        row = dict(row)
        row["nick"] = nick
        row["done_by"] = nick
        row["result"] = "DONE"
        done.append(row)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [], "done": done},
    )


def test_refresh_ci_failed_new_sha_offers_fix(tmp_path: Path):
    """Fail @ SHA1, FIX DONE, tip moves to SHA2 and fails -> new FIX for SHA2."""
    home = _home(tmp_path)
    mrb_merge_on_green.enqueue(
        home,
        repo=REPO,
        pr="4049",
        pass_sha=SHA1,
        url=f"https://github.com/{REPO}/pull/4049",
    )
    gitclaim.stamp_mrb_done(home, REPO, "#4049")

    def fetch_pr_sha1(repo: str, pr: str) -> dict:
        return {
            "repo": repo,
            "pr": pr,
            "sha": SHA1,
            "merged": False,
            "closed": False,
            "labels": [],
            "title": "tip",
            "body": "",
            "checks": "failure",
            "html_url": f"https://github.com/{repo}/pull/{pr}",
        }

    summary = mrb_merge_on_green.process_pending(
        home,
        fetch_pr=fetch_pr_sha1,
        fetch_comments=lambda *_a, **_k: [],
        merge_fn=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no merge")),
        token=None,
    )
    assert summary["ci_failed"] == 1
    assert summary.get("fix_offered", 0) >= 1
    live = [
        r
        for r in gitclaim.load_queue(home).get("unaccepted") or []
        if str(r.get("task") or "").upper() == "FIX"
    ]
    assert len(live) == 1
    assert mrb_merge_on_green.shas_match(str(live[0].get("pass_sha") or ""), SHA1)
    _finish_fix(home)

    # Tip advanced + failed again: refresh parked rows without a pending poll entry.
    def fetch_pr_sha2(repo: str, pr: str) -> dict:
        return {
            "repo": repo,
            "pr": pr,
            "sha": SHA2,
            "merged": False,
            "closed": False,
            "labels": [],
            "title": "tip",
            "body": "",
            "checks": "failure",
            "html_url": f"https://github.com/{repo}/pull/{pr}",
        }

    out = mrb_merge_on_green.refresh_ci_failed_tips(
        home,
        fetch_pr=fetch_pr_sha2,
        main_red=False,
        token=None,
        force=True,
    )
    assert out["offered"] == 1
    assert out["deduped"] == 0
    live2 = [
        r
        for r in gitclaim.load_queue(home).get("unaccepted") or []
        if str(r.get("task") or "").upper() == "FIX"
    ]
    assert len(live2) == 1
    assert mrb_merge_on_green.shas_match(str(live2[0].get("pass_sha") or ""), SHA2)
    led = mrb_merge_on_green.load_ledger(home)
    parked = led["ci_failed"][f"{REPO}#4049"]
    assert mrb_merge_on_green.shas_match(str(parked.get("pass_sha") or ""), SHA2)


def test_refresh_ci_failed_same_sha_dedupes(tmp_path: Path):
    home = _home(tmp_path)
    doc = mrb_merge_on_green.load_ledger(home)
    mrb_merge_on_green.park_ci_failed(
        doc,
        {
            "repo": REPO,
            "pr": "4054",
            "pass_sha": SHA1,
            "url": f"https://github.com/{REPO}/pull/4054",
        },
        detail="failure",
    )
    mrb_merge_on_green.save_ledger(home, doc)
    first = mrb_merge_on_green.enqueue_fix_ci(
        home,
        repo=REPO,
        pr="4054",
        pass_sha=SHA1,
        detail="failure",
        main_red=False,
    )
    assert first == "added"

    def fetch_pr(repo: str, pr: str) -> dict:
        return {
            "repo": repo,
            "pr": pr,
            "sha": SHA1,
            "merged": False,
            "closed": False,
            "labels": [],
            "title": "tip",
            "body": "",
            "checks": "failure",
            "html_url": f"https://github.com/{repo}/pull/{pr}",
        }

    out = mrb_merge_on_green.refresh_ci_failed_tips(
        home,
        fetch_pr=fetch_pr,
        main_red=False,
        force=True,
    )
    assert out["offered"] == 0
    assert out["deduped"] == 1
    live = [
        r
        for r in gitclaim.load_queue(home).get("unaccepted") or []
        if str(r.get("task") or "").upper() == "FIX"
    ]
    assert len(live) == 1


def test_check_run_failure_offers_fix_for_new_sha(tmp_path: Path):
    home = _home(tmp_path)
    doc = mrb_merge_on_green.load_ledger(home)
    mrb_merge_on_green.park_ci_failed(
        doc,
        {
            "repo": REPO,
            "pr": "4049",
            "pass_sha": SHA1,
            "url": f"https://github.com/{REPO}/pull/4049",
        },
        detail="failure",
    )
    mrb_merge_on_green.save_ledger(home, doc)
    mrb_merge_on_green.enqueue_fix_ci(
        home, repo=REPO, pr="4049", pass_sha=SHA1, detail="failure", main_red=False
    )
    _finish_fix(home)

    payload = {
        "action": "completed",
        "check_run": {
            "id": 99,
            "head_sha": SHA2,
            "status": "completed",
            "conclusion": "failure",
            "name": "test-and-synth",
            "pull_requests": [{"number": 4049}],
        },
        "repository": {"full_name": REPO},
    }
    result = mrb_merge_on_green.handle_check_run_event(
        home, payload, main_red=False
    )
    assert result == "added"
    live = [
        r
        for r in gitclaim.load_queue(home).get("unaccepted") or []
        if str(r.get("task") or "").upper() == "FIX"
    ]
    assert len(live) == 1
    assert mrb_merge_on_green.shas_match(str(live[0].get("pass_sha") or ""), SHA2)


def test_check_run_failure_same_sha_dedupes(tmp_path: Path):
    home = _home(tmp_path)
    doc = mrb_merge_on_green.load_ledger(home)
    mrb_merge_on_green.park_ci_failed(
        doc,
        {
            "repo": REPO,
            "pr": "4054",
            "pass_sha": SHA1,
            "url": f"https://github.com/{REPO}/pull/4054",
        },
        detail="failure",
    )
    mrb_merge_on_green.save_ledger(home, doc)
    assert (
        mrb_merge_on_green.enqueue_fix_ci(
            home, repo=REPO, pr="4054", pass_sha=SHA1, detail="failure", main_red=False
        )
        == "added"
    )
    payload = {
        "action": "completed",
        "check_run": {
            "id": 100,
            "head_sha": SHA1,
            "status": "completed",
            "conclusion": "failure",
            "name": "test-and-synth",
            "pull_requests": [{"number": 4054}],
        },
        "repository": {"full_name": REPO},
    }
    assert (
        mrb_merge_on_green.handle_check_run_event(home, payload, main_red=False)
        == "duplicate"
    )
    live = [
        r
        for r in gitclaim.load_queue(home).get("unaccepted") or []
        if str(r.get("task") or "").upper() == "FIX"
    ]
    assert len(live) == 1


def test_check_run_ignored_when_pr_unknown(tmp_path: Path):
    home = _home(tmp_path)
    payload = {
        "action": "completed",
        "check_run": {
            "id": 1,
            "head_sha": SHA1,
            "status": "completed",
            "conclusion": "failure",
            "name": "test",
            "pull_requests": [{"number": 9999}],
        },
        "repository": {"full_name": REPO},
    }
    assert mrb_merge_on_green.handle_check_run_event(home, payload) == "skipped"


def test_process_pending_sweeps_parked_ci_failed(tmp_path: Path):
    """process_pending must refresh parked tips even when pending is empty."""
    home = _home(tmp_path)
    doc = mrb_merge_on_green.load_ledger(home)
    mrb_merge_on_green.park_ci_failed(
        doc,
        {
            "repo": REPO,
            "pr": "4049",
            "pass_sha": SHA1,
            "url": f"https://github.com/{REPO}/pull/4049",
        },
        detail="failure",
    )
    mrb_merge_on_green.save_ledger(home, doc)
    mrb_merge_on_green.enqueue_fix_ci(
        home, repo=REPO, pr="4049", pass_sha=SHA1, detail="failure", main_red=False
    )
    _finish_fix(home)
    # Due for refresh immediately (chair tick after CI_FAILED_REFRESH_S).
    led = mrb_merge_on_green.load_ledger(home)
    parked = led["ci_failed"][f"{REPO}#4049"]
    parked["next_refresh_epoch"] = 0
    mrb_merge_on_green.save_ledger(home, led)

    def fetch_pr(repo: str, pr: str) -> dict:
        return {
            "repo": repo,
            "pr": pr,
            "sha": SHA2,
            "merged": False,
            "closed": False,
            "labels": [],
            "title": "tip",
            "body": "",
            "checks": "failure",
            "html_url": f"https://github.com/{repo}/pull/{pr}",
        }

    summary = mrb_merge_on_green.process_pending(
        home,
        fetch_pr=fetch_pr,
        fetch_comments=lambda *_a, **_k: [],
        merge_fn=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no merge")),
    )
    assert summary.get("ci_failed_refresh_offered", 0) == 1
    live = [
        r
        for r in gitclaim.load_queue(home).get("unaccepted") or []
        if str(r.get("task") or "").upper() == "FIX"
    ]
    assert len(live) == 1
    assert mrb_merge_on_green.shas_match(str(live[0].get("pass_sha") or ""), SHA2)
