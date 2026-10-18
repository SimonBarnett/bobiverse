"""FR #4714: requeue_sha must not drop a head that already has a PASS board."""
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

OLD_SHA = "7" + "d" * 39
NEW_SHA = "7" + "a" * 39
REPO = "SimonBarnett/a-search"
PR = "4250"


def _boards() -> list[dict]:
    return [
        {
            "user": {"login": "win-mpre8vi4u6u-5772"},
            "author_association": "NONE",
            "body": f"## MRB board\n\n**Verdict:** PASS\nMRB PASS @ {OLD_SHA}\n",
            "created_at": "2026-10-18T16:25:12Z",
        },
        {
            "user": {"login": "win-mpre8vi4u6u-5772"},
            "author_association": "NONE",
            "body": f"## MRB board\n\n**Verdict:** PASS\nMRB PASS @ {NEW_SHA}\n",
            "created_at": "2026-10-18T16:25:53Z",
        },
    ]


def _pr(**extra: object) -> dict:
    state = {
        "repo": REPO,
        "pr": PR,
        "sha": NEW_SHA,
        "merged": False,
        "closed": False,
        "labels": [],
        "title": "passed then conflicting",
        "body": "",
        "checks": "success",
        "html_url": f"https://github.com/{REPO}/pull/{PR}",
        "mergeable": "MERGEABLE",
        "mergeable_state": "CLEAN",
    }
    state.update(extra)
    return state


def _mrb_rows(home: Path) -> list[dict]:
    q = gitclaim.load_queue(home)
    return [
        r
        for r in (q.get("unaccepted") or [])
        if isinstance(r, dict) and str(r.get("task") or "").upper() == "MRB"
    ]


def test_requeue_sha_keeps_pending_when_head_already_passed(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    mrb_merge_on_green.enqueue(
        home, repo=REPO, pr=PR, pass_sha=OLD_SHA, url=f"https://github.com/{REPO}/pull/{PR}"
    )
    merged: list[str] = []

    summary = mrb_merge_on_green.process_pending(
        home,
        fetch_pr=lambda repo, pr: _pr(),
        fetch_comments=lambda r, p: _boards(),
        merge_fn=lambda repo, pr, sha: merged.append(sha),
    )
    assert summary["requeued"] == 0
    assert _mrb_rows(home) == []
    assert merged == [NEW_SHA]
    pending = mrb_merge_on_green.load_ledger(home)["pending"]
    assert pending == []


def test_requeue_sha_dirty_head_with_pass_queues_fix_not_mrb(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    mrb_merge_on_green.enqueue(
        home, repo=REPO, pr=PR, pass_sha=OLD_SHA, url=f"https://github.com/{REPO}/pull/{PR}"
    )

    summary = mrb_merge_on_green.process_pending(
        home,
        fetch_pr=lambda repo, pr: _pr(mergeable="CONFLICTING", mergeable_state="DIRTY"),
        fetch_comments=lambda r, p: _boards(),
        merge_fn=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not merge")),
    )
    assert summary["requeued"] == 0
    assert summary.get("conflict_parked") == 1
    assert _mrb_rows(home) == []
    q = gitclaim.load_queue(home)
    fix = [
        r
        for r in (q.get("unaccepted") or [])
        if isinstance(r, dict) and str(r.get("task") or "").upper() == "FIX"
    ]
    assert len(fix) == 1
    assert mrb_merge_on_green.load_ledger(home)["pending"] == []
