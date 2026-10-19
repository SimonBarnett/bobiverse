"""FR #4585: PASSed+auto-merge + red required CI offers one deduped FIX, not MRB."""
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

PASS_SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
REPO = "SimonBarnett/a-search"


def _board() -> list[dict]:
    return [
        {
            "user": {"login": "flamingo-1"},
            "author_association": "NONE",
            "body": f"## MRB board\n**Verdict:** PASS\nMRB PASS @ {PASS_SHA}",
            "created_at": "2026-10-17T06:00:00Z",
        }
    ]


def _pr(checks: str, *, sha: str = PASS_SHA, pr: str = "1796"):
    def fetch(repo: str, num: str) -> dict:
        return {
            "repo": repo,
            "pr": num,
            "sha": sha,
            "merged": False,
            "closed": False,
            "labels": [],
            "title": "fix",
            "body": "",
            "checks": checks,
            "html_url": f"https://github.com/{repo}/pull/{num}",
        }

    return fetch


def _no_merge(*_a, **_k):
    raise AssertionError("must not merge")


def test_failure_signature_shared_across_prs():
    # FR #4596: shared collapse only when main_red=True.
    a = mrb_merge_on_green.failure_signature(REPO, detail="failure", pr="1", main_red=True)
    b = mrb_merge_on_green.failure_signature(REPO, detail="failure", pr="2", main_red=True)
    assert a == b
    assert REPO.split("/")[-1] in a or "a-search" in a.lower() or "SimonBarnett" in a


def test_ci_failed_parks_and_offers_one_fix(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(
        mrb_merge_on_green, "main_branch_checks_red", lambda *_a, **_k: True
    )
    mrb_merge_on_green.enqueue(
        home, repo=REPO, pr="1796", pass_sha=PASS_SHA, url=f"https://github.com/{REPO}/pull/1796"
    )
    logs: list[str] = []
    summary = mrb_merge_on_green.process_pending(
        home,
        fetch_pr=_pr("failure"),
        fetch_comments=lambda *_a, **_k: _board(),
        merge_fn=_no_merge,
        log=logs.append,
        now=lambda: 2_000_000.0,
    )
    assert summary["ci_failed"] == 1
    assert summary.get("fix_offered") == 1
    assert summary["requeued"] == 0
    q = gitclaim.load_queue(home)
    fixes = [
        r
        for r in (q.get("unaccepted") or [])
        if isinstance(r, dict) and str(r.get("task") or "").upper() == "FIX"
    ]
    assert len(fixes) == 1
    assert str(fixes[0].get("id") or "") == "#1796"
    body = str(fixes[0].get("body") or "") + " " + str(fixes[0].get("title") or "")
    assert "4585" in body or "4596" in body
    # No MRB requeue for the same PR.
    assert not any(
        str(r.get("task") or "").upper() == "MRB" and str(r.get("id") or "").lstrip("#") == "1796"
        for r in (q.get("unaccepted") or [])
        if isinstance(r, dict)
    )


def test_second_parked_pr_same_signature_does_not_second_fix(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    # FR #4596: collapse only when main itself is red.
    monkeypatch.setattr(
        mrb_merge_on_green, "main_branch_checks_red", lambda *_a, **_k: True
    )
    for pr in ("1796", "1800"):
        mrb_merge_on_green.enqueue(
            home,
            repo=REPO,
            pr=pr,
            pass_sha=PASS_SHA,
            url=f"https://github.com/{REPO}/pull/{pr}",
        )
    mrb_merge_on_green.process_pending(
        home,
        fetch_pr=_pr("failure", pr="1796"),
        fetch_comments=lambda *_a, **_k: _board(),
        merge_fn=_no_merge,
        now=lambda: 2_000_000.0,
    )
    mrb_merge_on_green.process_pending(
        home,
        fetch_pr=_pr("failure", pr="1800"),
        fetch_comments=lambda *_a, **_k: _board(),
        merge_fn=_no_merge,
        now=lambda: 2_000_060.0,
    )
    q = gitclaim.load_queue(home)
    fixes = [
        r
        for r in (q.get("unaccepted") or [])
        if isinstance(r, dict) and str(r.get("task") or "").upper() == "FIX"
    ]
    assert len(fixes) == 1


def test_canon_task_keeps_fix_on_assign_wire():
    row = {"task": "FIX", "repo": REPO, "id": "#1796", "url": f"https://github.com/{REPO}/pull/1796"}
    assert gitclaim._canon_task(row) == "FIX"
    line = gitclaim.format_assign_line("flamingo-1", row)
    assert line.startswith("flamingo-1: FIX ")
    assert "/pull/1796" in line
