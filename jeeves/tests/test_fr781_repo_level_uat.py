"""FR #781: port gh-Jeeves#239 — UAT is per REPO (#0), never per-PR.

Source (closed superseded): https://github.com/SimonBarnett/gh-Jeeves/pull/239
Also closes the originating gap bobiverse#768.
"""
from __future__ import annotations

from pathlib import Path

import gitclaim


REPO = "SimonBarnett/bobiverse"


def _home(tmp_path: Path) -> Path:
    h = tmp_path / "chair"
    h.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(h),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return h


def test_is_mrb_fix_pr_title_shapes():
    assert gitclaim.is_mrb_fix_pr_title("fix(mrb-229): refuse cross-repo")
    assert gitclaim.is_mrb_fix_pr_title("mrb-229-fix: refuse cross-repo")
    assert not gitclaim.is_mrb_fix_pr_title("fix(bobiverse#247): never invent")
    assert not gitclaim.is_mrb_fix_pr_title("docs(mrb-229): note")


def test_merged_pr_webhook_does_not_enqueue_per_pr_uat(tmp_path: Path):
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": REPO,
                    "task": "MRB",
                    "id": "#229",
                    "line": "fix(bobiverse#247)",
                    "url": f"https://github.com/{REPO}/pull/229",
                }
            ],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    claim = gitclaim.claim_from_payload(
        "pull_request",
        {
            "action": "closed",
            "repository": {"full_name": REPO},
            "pull_request": {
                "number": 229,
                "title": "fix(bobiverse#247): never invent MRB /pull/N",
                "html_url": f"https://github.com/{REPO}/pull/229",
                "body": "Closes SimonBarnett/bobiverse#247",
                "merged": True,
            },
        },
    )
    assert claim is not None and claim.task == "MRB" and claim.merged is True
    gitclaim.apply_queue_event(home, claim)
    q = gitclaim.load_queue(home)
    assert not any(str(r.get("task") or "").upper() == "UAT" for r in q["unaccepted"])
    assert not any(str(r.get("task") or "").upper() == "MRB" for r in q["unaccepted"])


def test_mrb_fix_pr_opened_does_not_enqueue_mrb():
    claim = gitclaim.claim_from_payload(
        "pull_request",
        {
            "action": "opened",
            "repository": {"full_name": REPO},
            "pull_request": {
                "number": 237,
                "title": "mrb-229-fix: refuse cross-repo MRB pull URLs",
                "html_url": f"https://github.com/{REPO}/pull/237",
                "body": "Refs #229",
                "merged": False,
            },
        },
    )
    assert claim is None


def test_offer_skips_legacy_per_pr_uat(tmp_path: Path):
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": REPO,
                    "task": "UAT",
                    "id": "#229",
                    "pr_id": "#229",
                    "line": "fix(bobiverse#247)",
                    "url": f"https://github.com/{REPO}/pull/229",
                    "seq": 1,
                },
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#10",
                    "line": "next",
                    "url": "https://github.com/SimonBarnett/bobiverse/issues/10",
                    "seq": 2,
                },
            ],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    st, job = gitclaim.offer_focus_top(home, "marchhare-1", "#marchhare")
    assert st == "ok"
    assert job is not None
    assert (job.get("task"), job.get("id")) == ("FR", "#10")


def test_offer_repo_level_uat(tmp_path: Path):
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": REPO,
                    "task": "UAT",
                    "id": "#0",
                    "repo_uat": True,
                    "merged_prs": ["#229"],
                    "line": f"UAT {REPO}: all issues closed, all PRs merged",
                    "url": f"https://github.com/{REPO}",
                    "seq": 1,
                }
            ],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    st, job = gitclaim.offer_focus_top(home, "marchhare-1", "#marchhare")
    assert st == "ok" and job is not None
    assert (job.get("task"), job.get("id")) == ("UAT", "#0")
    assert job.get("repo_uat") is True
    assert gitclaim.format_assign_line("marchhare-1", job).startswith(
        f"marchhare-1: UAT {REPO}#0 "
    )
