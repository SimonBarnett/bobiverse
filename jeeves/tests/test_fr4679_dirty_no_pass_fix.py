"""FR #4679: DIRTY/CONFLICTING open PRs get a FIX even with no MRB PASS."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

gitclaim = importlib.import_module("gitclaim")

SHA = "b" * 40
REPO = "SimonBarnett/a-search"


def _home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    return home


def _resync(home: Path, pr: dict) -> list[dict]:
    def fetch_json(url: str):
        if "/pulls" in url and "state=closed" not in url:
            return [pr]
        if "/issues" in url:
            return []
        return []

    gitclaim.resync_from_github(home, [REPO], fetch_json=fetch_json)
    q = gitclaim.load_queue(home)
    return list(q.get("unaccepted") or []) + list(q.get("accepted") or [])


def test_dirty_green_auto_merge_no_pass_queues_fix(tmp_path: Path):
    """Harvest tip: DIRTY + green CI + auto-merge, never PASSed -> one FIX."""
    home = _home(tmp_path)
    pr = {
        "number": 1466,
        "title": "lesson(harvest-agent-skills): stranded dirty tip",
        "body": "harvest tip",
        "html_url": f"https://github.com/{REPO}/pull/1466",
        "state": "open",
        "draft": False,
        "auto_merge": {"merge_method": "squash"},
        "head": {"sha": SHA},
        "user": {"login": "u"},
        "labels": [{"name": "harvest-lesson"}, {"name": "via-intake"}],
        "mergeable": "CONFLICTING",
        "mergeable_state": "DIRTY",
        "mergeStateStatus": "DIRTY",
        "checks": "success",
    }
    rows = _resync(home, pr)
    fix = [r for r in rows if str(r.get("task") or "").upper() == "FIX"]
    mrb = [r for r in rows if str(r.get("task") or "").upper() == "MRB"]
    assert len(fix) == 1, rows
    assert len(mrb) == 0, rows
    blob = str(fix[0].get("body") or "") + " " + str(fix[0].get("title") or "")
    assert "conflict" in blob.lower()
    assert "1466" in blob


def test_dirty_cancelled_no_auto_queues_fix(tmp_path: Path):
    """Product tip: DIRTY + cancelled CI + no auto-merge -> one FIX."""
    home = _home(tmp_path)
    pr = {
        "number": 3744,
        "title": "fix: product stranded dirty",
        "body": f"Closes {REPO}#99",
        "html_url": f"https://github.com/{REPO}/pull/3744",
        "state": "open",
        "draft": False,
        "auto_merge": None,
        "head": {"sha": SHA},
        "user": {"login": "u"},
        "labels": [],
        "mergeable": "CONFLICTING",
        "mergeable_state": "DIRTY",
        "checks": "completed/cancelled",
    }
    rows = _resync(home, pr)
    fix = [r for r in rows if str(r.get("task") or "").upper() == "FIX"]
    mrb = [r for r in rows if str(r.get("task") or "").upper() == "MRB"]
    assert len(fix) == 1, rows
    assert len(mrb) == 0, rows


def test_dirty_fix_not_duplicated_while_live(tmp_path: Path):
    home = _home(tmp_path)
    pr = {
        "number": 1807,
        "title": "lesson(harvest-agent-skills): twin dirty",
        "body": "harvest tip",
        "html_url": f"https://github.com/{REPO}/pull/1807",
        "state": "open",
        "draft": False,
        "auto_merge": {"merge_method": "merge"},
        "head": {"sha": SHA},
        "user": {"login": "u"},
        "labels": [{"name": "harvest-lesson"}],
        "mergeable": "CONFLICTING",
        "mergeable_state": "DIRTY",
        "checks": "success",
    }
    rows1 = _resync(home, pr)
    assert len([r for r in rows1 if str(r.get("task") or "").upper() == "FIX"]) == 1
    rows2 = _resync(home, pr)
    fix = [r for r in rows2 if str(r.get("task") or "").upper() == "FIX"]
    assert len(fix) == 1, rows2
