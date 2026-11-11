"""Hostile pins for MRB #6045 / FR #6044 (docs/mrb dirty FIX, not MRB)."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

gitclaim = importlib.import_module("gitclaim")
mog = importlib.import_module("mrb_merge_on_green")

SHA = "c" * 40
REPO = "SimonBarnett/bobiverse"


def _home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    return home


def _docs_mrb_pr(**extra) -> dict:
    row = {
        "number": 6011,
        "title": "docs/mrb-6005: hostile pins for sqlcmd form walk",
        "body": "Refs SimonBarnett/bobiverse#6005",
        "html_url": f"https://github.com/{REPO}/pull/6011",
        "state": "open",
        "draft": False,
        "auto_merge": None,
        "head": {"sha": SHA, "ref": "docs/mrb-6005"},
        "base": {"ref": "main"},
        "user": {"login": "u"},
        "labels": [],
        "checks": "success",
    }
    row.update(extra)
    return row


def _merged_6005() -> dict:
    return {
        "number": 6005,
        "title": "FR #5991: sqlcmd form walk",
        "html_url": f"https://github.com/{REPO}/pull/6005",
        "state": "closed",
        "merged": True,
        "merged_at": "2026-11-02T19:46:00Z",
        "head": {"sha": "a" * 40, "ref": "fr-5991"},
        "base": {"ref": "main"},
    }


def _resync(home: Path, open_prs: list, details: dict) -> list:
    def fetch_json(url: str):
        u = str(url or "")
        for n, det in details.items():
            if f"/pulls/{n}" in u and "/pulls?" not in u:
                return det
        if "/pulls" in u and "state=closed" not in u:
            return list(open_prs)
        if "/issues" in u:
            return []
        return []

    gitclaim.resync_from_github(home, [REPO], fetch_json=fetch_json)
    q = gitclaim.load_queue(home)
    return list(q.get("unaccepted") or []) + list(q.get("accepted") or [])


def test_mrb6045_clean_docs_mrb_still_skipped(tmp_path: Path):
    # FR #6340 / #6511: clean orphan docs/mrb pin queues as one MRB (no longer skipped).
    home = _home(tmp_path)
    pr = _docs_mrb_pr(mergeable=True, mergeable_state="clean")
    rows = _resync(home, [pr], {6011: pr})
    jobs = [
        r
        for r in rows
        if str(r.get("task") or "").upper() == "MRB"
        and "6011" in str(r.get("id") or r.get("url") or "")
    ]
    assert len(jobs) == 1, rows
    assert jobs[0].get("task") == "MRB"
    fix = [
        r
        for r in rows
        if str(r.get("task") or "").upper() == "FIX"
        and "6011" in str(r.get("id") or r.get("url") or "")
    ]
    assert fix == []


def test_mrb6045_dirty_with_merged_original_queues_fix(tmp_path: Path):
    home = _home(tmp_path)
    pr = _docs_mrb_pr(mergeable=False, mergeable_state="dirty")
    rows = _resync(home, [pr], {6011: pr, 6005: _merged_6005()})
    jobs = [
        r
        for r in rows
        if str(r.get("task") or "").upper() == "FIX"
        and "6011" in str(r.get("id") or r.get("url") or "")
    ]
    assert jobs, rows
    mrb = [r for r in rows if str(r.get("task") or "").upper() == "MRB"]
    assert mrb == []


def test_mrb6045_enrich_keeps_false_when_detail_mergeable_null():
    pr = {"number": 6011, "mergeable": False}
    assert gitclaim.list_pr_needs_mergeability_enrichment(pr) is True

    def fetch_json(_url):
        return {"mergeable": None, "mergeable_state": "unknown"}

    gitclaim.enrich_pr_mergeability(pr, repo=REPO, num=6011, fetch_json=fetch_json)
    assert pr.get("mergeable") is False
    assert pr.get("mergeable_state") == "unknown"
    assert mog.merge_attempt_conflict_reason(
        mergeable=pr.get("mergeable"),
        merge_state=str(pr.get("mergeable_state") or ""),
    ) == "conflicting"
