"""FR #9924: required CI red under live MRB hold resets hold and queues FIX."""
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

REPO = "SimonBarnett/bobiverse"
SHA = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
NICK = "redqueen-1"


def test_ci_failure_triggers_mrb_reset_hard_vs_soft():
    assert mrb_merge_on_green.ci_failure_triggers_mrb_reset("failure") is True
    assert mrb_merge_on_green.ci_failure_triggers_mrb_reset("failure:build-jeeves") is True
    assert (
        mrb_merge_on_green.ci_failure_triggers_mrb_reset("failure:pytest-ascii-bom")
        is False
    )
    assert mrb_merge_on_green.ci_failure_triggers_mrb_reset("failure:lock") is False
    assert mrb_merge_on_green.ci_failure_triggers_mrb_reset("success") is False
    assert mrb_merge_on_green.ci_failure_triggers_mrb_reset("pending") is False


def test_rollup_soft_only_annotates_ascii_bom():
    runs = {
        "check_runs": [
            {
                "name": "pytest-ascii-bom",
                "status": "completed",
                "conclusion": "failure",
            }
        ]
    }
    assert mrb_merge_on_green.rollup_check_runs(runs) == "failure:pytest-ascii-bom"


def test_clear_live_mrb_hold_moves_accepted_to_done_ci_red(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    doc = gitclaim._empty_queue()
    doc["accepted"] = [
        {
            "repo": REPO,
            "task": "MRB",
            "id": "#9917",
            "nick": NICK,
            "accepted_by": NICK,
            "url": f"https://github.com/{REPO}/pull/9917",
        }
    ]
    doc["unaccepted"] = [
        {
            "repo": REPO,
            "task": "MRB",
            "id": "#9917",
            "offered_to": "flamingo-2",
            "url": f"https://github.com/{REPO}/pull/9917",
        }
    ]
    holders = gitclaim.clear_live_mrb_hold_for_ci_red(doc, REPO, "#9917")
    assert NICK in holders
    assert "flamingo-2" in holders
    assert not any(
        str(r.get("task") or "").upper() == "MRB"
        for r in (doc.get("accepted") or []) + (doc.get("unaccepted") or [])
        if isinstance(r, dict)
    )
    done_mrb = [
        r
        for r in (doc.get("done") or [])
        if isinstance(r, dict) and str(r.get("task") or "").upper() == "MRB"
    ]
    assert len(done_mrb) == 1
    assert str(done_mrb[0].get("result") or "") == "CI-RED"


def test_reset_live_mrb_hold_on_ci_red_enqueues_fix(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [
                {
                    "repo": REPO,
                    "task": "MRB",
                    "id": "#9917",
                    "nick": NICK,
                    "accepted_by": NICK,
                    "url": f"https://github.com/{REPO}/pull/9917",
                }
            ],
            "done": [],
        },
    )
    monkeypatch.setattr(
        mrb_merge_on_green,
        "fetch_pr_state",
        lambda *_a, **_k: {
            "sha": SHA,
            "merged": False,
            "closed": False,
            "title": "tip",
            "labels": [],
        },
    )
    result = mrb_merge_on_green.reset_live_mrb_hold_on_ci_red(
        home,
        repo=REPO,
        pr="9917",
        sha=SHA,
        url=f"https://github.com/{REPO}/pull/9917",
        detail="failure",
    )
    assert result == "added"
    q = gitclaim.load_queue(home)
    assert not any(
        str(r.get("task") or "").upper() == "MRB" and str(r.get("id") or "") == "#9917"
        for r in (q.get("accepted") or [])
        if isinstance(r, dict)
    )
    fixes = [
        r
        for r in (q.get("unaccepted") or [])
        if isinstance(r, dict) and str(r.get("task") or "").upper() == "FIX"
    ]
    assert len(fixes) == 1
    assert str(fixes[0].get("id") or "") == "#9917"
    blob = str(fixes[0].get("body") or "") + " " + str(fixes[0].get("title") or "")
    assert "9924" in blob
    # Soft-only must not reset / enqueue
    result2 = mrb_merge_on_green.reset_live_mrb_hold_on_ci_red(
        home,
        repo=REPO,
        pr="9918",
        sha=SHA,
        detail="failure:pytest-ascii-bom",
    )
    assert result2 == "skipped"


def test_soft_only_no_hold_path_returns_no_hold_or_skipped(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    gitclaim._write_queue(gitclaim.queue_path(home), gitclaim._empty_queue())
    assert (
        mrb_merge_on_green.reset_live_mrb_hold_on_ci_red(
            home, repo=REPO, pr="1", sha=SHA, detail="failure"
        )
        == "no-hold"
    )
