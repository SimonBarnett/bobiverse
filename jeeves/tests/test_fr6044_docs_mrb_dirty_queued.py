"""FR #6044: dirty green docs/mrb PR (original already merged) must get a job."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

gitclaim = importlib.import_module("gitclaim")

SHA = "c" * 40
REPO = "SimonBarnett/bobiverse"


def _home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    return home


def _resync(home: Path, pr: dict, *, detail: dict | None = None) -> list[dict]:
    def fetch_json(url: str):
        u = str(url or "")
        if f"/pulls/{pr.get('number')}" in u and "/pulls?" not in u:
            return detail if detail is not None else pr
        if "/pulls" in u and "state=closed" not in u:
            return [pr]
        if "/issues" in u:
            return []
        return []

    gitclaim.resync_from_github(home, [REPO], fetch_json=fetch_json)
    q = gitclaim.load_queue(home)
    return list(q.get("unaccepted") or []) + list(q.get("accepted") or [])


def _docs_mrb_pr(**extra) -> dict:
    row = {
        "number": 6011,
        "title": "docs/mrb-6005: hostile pins for sqlcmd form walk",
        "body": "Refs SimonBarnett/bobiverse#6005\n\nAdditive hostile tests.",
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


def _assert_job(rows: list[dict]) -> dict:
    jobs = [
        r
        for r in rows
        if str(r.get("task") or "").upper() in ("FIX", "MRB")
        and "6011" in str(r.get("id") or r.get("url") or r.get("title") or "")
    ]
    assert jobs, rows
    return jobs[0]


def test_fr6044_docs_mrb_dirty_rest_shape_queues_fix(tmp_path: Path):
    """GitHub REST: mergeable false + mergeable_state dirty; parent #6005 not open."""
    home = _home(tmp_path)
    pr = _docs_mrb_pr(mergeable=False, mergeable_state="dirty")
    rows = _resync(home, pr)
    job = _assert_job(rows)
    assert str(job.get("task") or "").upper() == "FIX"


def test_fr6044_docs_mrb_list_omits_mergeable_enriches_dirty(tmp_path: Path):
    """Open-PR list has no mergeable*; detail GET says dirty."""
    home = _home(tmp_path)
    pr = _docs_mrb_pr()
    detail = _docs_mrb_pr(mergeable=False, mergeable_state="dirty")
    rows = _resync(home, pr, detail=detail)
    job = _assert_job(rows)
    assert str(job.get("task") or "").upper() == "FIX"


def test_fr6044_docs_mrb_mergeable_false_without_state_queues_fix(tmp_path: Path):
    """Boolean mergeable false and no state must not skip the dirty FIX path."""
    home = _home(tmp_path)
    pr = _docs_mrb_pr(mergeable=False)
    rows = _resync(home, pr)
    job = _assert_job(rows)
    assert str(job.get("task") or "").upper() == "FIX"
