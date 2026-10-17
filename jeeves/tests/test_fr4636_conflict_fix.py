"""FR #4636: HTTP 405 / DIRTY stops merge-on-green and queues one conflict FIX."""
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

PASS_SHA = "a" * 40
NEW_SHA = "b" * 40
REPO = "SimonBarnett/a-search"
PR = "3702"


def _pass_board(sha: str = PASS_SHA) -> list[dict]:
    return [
        {
            "user": {"login": "marchhare-1"},
            "author_association": "NONE",
            "body": f"## MRB board\n\n**Verdict:** PASS\nMRB PASS @ {sha}\n",
            "created_at": "2026-10-17T18:00:00Z",
        }
    ]


def _ready(sha: str, **extra: object) -> dict:
    state = {
        "repo": REPO,
        "pr": PR,
        "sha": sha,
        "merged": False,
        "closed": False,
        "labels": [],
        "title": "conflicting tip",
        "body": "",
        "checks": "success",
        "html_url": f"https://github.com/{REPO}/pull/{PR}",
        "mergeable": "MERGEABLE",
        "merge_state_status": "CLEAN",
    }
    state.update(extra)
    return state


def _fix_rows(home: Path) -> list[dict]:
    q = gitclaim.load_queue(home)
    return [
        r
        for r in (q.get("unaccepted") or [])
        if isinstance(r, dict) and str(r.get("task") or "").upper() == "FIX"
    ]


def test_http_405_stops_retry_and_queues_one_fix(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    mrb_merge_on_green.enqueue(
        home, repo=REPO, pr=PR, pass_sha=PASS_SHA, url=f"https://github.com/{REPO}/pull/{PR}"
    )
    calls: list[str] = []

    def merge_fn(repo: str, pr: str, sha: str) -> dict:
        calls.append(sha)
        raise RuntimeError(f"GitHub HTTP 405 for https://api.github.com/repos/{repo}/pulls/{pr}/merge")

    kwargs = dict(
        fetch_pr=lambda repo, pr: _ready(PASS_SHA),
        fetch_comments=lambda r, p: _pass_board(),
        merge_fn=merge_fn,
    )
    first = mrb_merge_on_green.process_pending(home, **kwargs)
    second = mrb_merge_on_green.process_pending(home, **kwargs)
    assert first["conflict_parked"] == 1
    assert first["merged"] == 0
    assert second["conflict_parked"] == 0
    assert calls == [PASS_SHA]
    assert mrb_merge_on_green.load_ledger(home)["pending"] == []
    blocked = mrb_merge_on_green.conflict_blocked_pass_sha(
        mrb_merge_on_green.load_ledger(home), REPO, PR
    )
    assert blocked == PASS_SHA
    assert len(_fix_rows(home)) == 1
    again = mrb_merge_on_green.enqueue_conflict_fix(
        home, repo=REPO, pr=PR, pass_sha=PASS_SHA, reason="http-405"
    )
    assert again == "duplicate"
    assert len(_fix_rows(home)) == 1


def test_dirty_state_does_not_call_merge(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    mrb_merge_on_green.enqueue(
        home, repo=REPO, pr=PR, pass_sha=PASS_SHA, url=f"https://github.com/{REPO}/pull/{PR}"
    )

    def merge_fn(*_a, **_k):
        raise AssertionError("must not PUT merge when DIRTY")

    summary = mrb_merge_on_green.process_pending(
        home,
        fetch_pr=lambda repo, pr: _ready(
            PASS_SHA, mergeable="CONFLICTING", merge_state_status="DIRTY"
        ),
        fetch_comments=lambda r, p: _pass_board(),
        merge_fn=merge_fn,
    )
    assert summary["conflict_parked"] == 1
    assert len(_fix_rows(home)) == 1


def test_new_sha_rearms_merge_on_green(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    mrb_merge_on_green.enqueue(
        home, repo=REPO, pr=PR, pass_sha=PASS_SHA, url=f"https://github.com/{REPO}/pull/{PR}"
    )
    mrb_merge_on_green.process_pending(
        home,
        fetch_pr=lambda repo, pr: _ready(
            PASS_SHA, mergeable="CONFLICTING", merge_state_status="DIRTY"
        ),
        fetch_comments=lambda r, p: _pass_board(),
        merge_fn=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no merge")),
    )
    assert mrb_merge_on_green.rearm_conflict_blocked(
        home, repo=REPO, pr=PR, head_sha=PASS_SHA
    ) == "blocked"
    assert mrb_merge_on_green.rearm_conflict_blocked(
        home, repo=REPO, pr=PR, head_sha=NEW_SHA
    ) == "rearmed"
    merged: list[str] = []
    summary = mrb_merge_on_green.process_pending(
        home,
        fetch_pr=lambda repo, pr: _ready(NEW_SHA),
        fetch_comments=lambda r, p: _pass_board(NEW_SHA),
        merge_fn=lambda repo, pr, sha: merged.append(sha) or {"merged": True},
    )
    assert summary["merged"] == 1
    assert merged == [NEW_SHA]
    assert mrb_merge_on_green.conflict_blocked_pass_sha(
        mrb_merge_on_green.load_ledger(home), REPO, PR
    ) == ""
