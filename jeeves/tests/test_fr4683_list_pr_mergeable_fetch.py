"""FR #4683: resync must fetch mergeability; open-PR list never returns it."""
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
REPO = "SimonBarnett/a-search"


def _home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    return home


def _list_shaped_pr(num: int = 1807) -> dict:
    """Shape of GET /repos/{repo}/pulls?state=open --- no mergeable* keys."""
    return {
        "number": num,
        "title": "lesson(harvest-agent-skills): stranded dirty tip",
        "body": "harvest tip",
        "html_url": f"https://github.com/{REPO}/pull/{num}",
        "state": "open",
        "draft": False,
        "auto_merge": {"merge_method": "squash"},
        "head": {"sha": SHA},
        "user": {"login": "u"},
        "labels": [{"name": "harvest-lesson"}],
        "checks": "success",
    }


def test_list_shaped_pr_triggers_detail_fetch_and_queues_fix(tmp_path: Path):
    home = _home(tmp_path)
    list_pr = _list_shaped_pr(1807)
    detail_hits: list[str] = []

    def fetch_json(url: str):
        if "/pulls/1807" in url and "state=" not in url:
            detail_hits.append(url)
            return {
                "number": 1807,
                "state": "open",
                "mergeable": False,
                "mergeable_state": "dirty",
                "head": {"sha": SHA},
            }
        if "/pulls" in url and "state=closed" not in url:
            return [list_pr]
        if "/issues" in url:
            return []
        return []

    gitclaim.resync_from_github(home, [REPO], fetch_json=fetch_json)
    q = gitclaim.load_queue(home)
    rows = list(q.get("unaccepted") or []) + list(q.get("accepted") or [])
    fix = [r for r in rows if str(r.get("task") or "").upper() == "FIX"]
    mrb = [r for r in rows if str(r.get("task") or "").upper() == "MRB"]
    assert detail_hits, "expected GET /pulls/N for mergeability"
    assert any(f"/repos/{REPO}/pulls/1807" in u for u in detail_hits)
    assert len(fix) == 1, rows
    assert len(mrb) == 0, rows
    assert "mergeable_state" in list_pr
    assert str(list_pr.get("mergeable_state")).lower() == "dirty"


def test_list_pr_with_mergeable_keys_skips_detail_fetch(tmp_path: Path):
    home = _home(tmp_path)
    pr = _list_shaped_pr(1466)
    pr["mergeable"] = "CONFLICTING"
    pr["mergeable_state"] = "DIRTY"
    detail_hits: list[str] = []

    def fetch_json(url: str):
        if "/pulls/1466" in url and "state=" not in url:
            detail_hits.append(url)
            return {"number": 1466, "mergeable_state": "dirty"}
        if "/pulls" in url and "state=closed" not in url:
            return [pr]
        if "/issues" in url:
            return []
        return []

    gitclaim.resync_from_github(home, [REPO], fetch_json=fetch_json)
    q = gitclaim.load_queue(home)
    rows = list(q.get("unaccepted") or []) + list(q.get("accepted") or [])
    fix = [r for r in rows if str(r.get("task") or "").upper() == "FIX"]
    assert len(fix) == 1, rows
    assert detail_hits == [], detail_hits


def test_list_pr_needs_mergeability_enrichment_helper():
    bare = {"number": 1, "title": "x"}
    assert gitclaim.list_pr_needs_mergeability_enrichment(bare) is True
    assert gitclaim.list_pr_needs_mergeability_enrichment({"mergeable": False}) is False
    assert gitclaim.list_pr_needs_mergeability_enrichment({"mergeable_state": "dirty"}) is False
    assert gitclaim.list_pr_needs_mergeability_enrichment({"mergeStateStatus": "DIRTY"}) is False
