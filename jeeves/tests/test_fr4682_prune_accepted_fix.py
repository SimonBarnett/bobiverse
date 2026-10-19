"""FR #4682: prune accepted/unaccepted FIX when the PR merges or closes."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

gitclaim = importlib.import_module("gitclaim")

REPO = "SimonBarnett/a-search"
SHA = "a" * 40


def _home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    return home


def _acc_fix(nick: str = "flamingo-33384", num: str = "#3871") -> dict:
    return {
        "task": "FIX",
        "repo": REPO,
        "id": num,
        "url": f"https://github.com/{REPO}/pull/{num.lstrip('#')}",
        "nick": nick,
        "accepted_by": nick,
        "title": f"FIX CI after MRB PASS (red check; PR {num})",
        "body": f"Head SHA {SHA}.",
        "pass_sha": SHA,
    }


def test_purge_dead_fix_accepted_merged_moves_to_done():
    doc = {
        "accepted": [_acc_fix()],
        "done": [],
        "unaccepted": [],
    }
    n = gitclaim._purge_dead_fix_accepted(
        doc,
        pr_exists=lambda r, n: False,
        pr_merged=lambda r, n: True,
        home=None,
    )
    assert n == 1
    assert doc["accepted"] == []
    assert len(doc["done"]) == 1
    assert doc["done"][0]["result"] == "MERGED"
    assert doc["done"][0].get("merged") is True


def test_purge_dead_fix_accepted_closed_unmerged_is_closed():
    doc = {
        "accepted": [_acc_fix(num="#3354")],
        "done": [],
        "unaccepted": [],
    }
    n = gitclaim._purge_dead_fix_accepted(
        doc,
        pr_exists=lambda r, n: False,
        pr_merged=lambda r, n: False,
        home=None,
    )
    assert n == 1
    assert doc["accepted"] == []
    assert doc["done"][0]["result"] == "CLOSED"
    assert doc["done"][0].get("merged") is not True


def test_purge_dead_fix_unaccepted_via_open_pulls():
    doc = {
        "unaccepted": [
            {
                "task": "FIX",
                "repo": REPO,
                "id": "#3871",
                "url": f"https://github.com/{REPO}/pull/3871",
            },
            {
                "task": "FIX",
                "repo": REPO,
                "id": "#9999",
                "url": f"https://github.com/{REPO}/pull/9999",
            },
        ],
        "accepted": [],
        "done": [],
    }
    n = gitclaim._purge_dead_fix_unaccepted(
        doc,
        open_pulls={REPO: {"#9999"}},
        fetched_repos={REPO},
    )
    assert n == 1
    ids = [str(r.get("id")) for r in doc["unaccepted"]]
    assert ids == ["#9999"]


def test_resync_drops_accepted_fix_when_pr_not_open(tmp_path: Path, monkeypatch):
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [_acc_fix()],
            "done": [],
        },
    )
    cleared: list[tuple[str, str]] = []

    def fake_clear(home_arg, nick, *, only_if_work_contains=""):
        cleared.append((nick, only_if_work_contains))
        return None

    monkeypatch.setattr(gitclaim.bobreport, "clear_seat_doing", fake_clear)

    def fetch_json(url: str):
        # PR #3871 is gone (merged). No open pulls.
        if "/pulls" in url and "state=closed" not in url:
            return []
        if "/issues" in url:
            return []
        return []

    gitclaim.resync_from_github(home, [REPO], fetch_json=fetch_json)
    q = gitclaim.load_queue(home)
    assert q.get("accepted") == []
    assert any(
        str(r.get("task") or "").upper() == "FIX"
        and str(r.get("id") or "") == "#3871"
        and str(r.get("result") or "") == "MERGED"
        for r in (q.get("done") or [])
    )
    assert any(n == "flamingo-33384" and "3871" in str(w) for n, w in cleared)


def test_closed_webhook_moves_accepted_fix_to_done(tmp_path: Path):
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "task": "FIX",
                    "repo": REPO,
                    "id": "#3871",
                    "url": f"https://github.com/{REPO}/pull/3871",
                }
            ],
            "accepted": [_acc_fix()],
            "done": [],
        },
    )
    claim = gitclaim.claim_from_payload(
        "pull_request",
        {
            "action": "closed",
            "repository": {"full_name": REPO},
            "pull_request": {
                "number": 3871,
                "merged": True,
                "html_url": f"https://github.com/{REPO}/pull/3871",
                "title": "fix stubs",
                "body": "",
                "user": {"login": "u"},
                "draft": False,
                "labels": [],
            },
        },
    )
    assert claim is not None
    changed = gitclaim.apply_queue_event(home, claim)
    assert changed in ("updated", "removed", "noop")
    q = gitclaim.load_queue(home)
    assert not any(
        str(r.get("task") or "").upper() == "FIX" and str(r.get("id") or "") == "#3871"
        for r in (q.get("unaccepted") or []) + (q.get("accepted") or [])
    )
    assert any(
        str(r.get("task") or "").upper() == "FIX"
        and str(r.get("id") or "") == "#3871"
        and str(r.get("result") or "") == "MERGED"
        for r in (q.get("done") or [])
    )


def test_resync_does_not_requeue_fix_for_missing_pr(tmp_path: Path):
    """Merged PR must not leave a live FIX row after resync."""
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "task": "FIX",
                    "repo": REPO,
                    "id": "#3871",
                    "url": f"https://github.com/{REPO}/pull/3871",
                    "title": "FIX CI after MRB PASS",
                }
            ],
            "accepted": [],
            "done": [],
        },
    )

    def fetch_json(url: str):
        if "/pulls" in url and "state=closed" not in url:
            return []
        if "/issues" in url:
            return []
        return []

    gitclaim.resync_from_github(home, [REPO], fetch_json=fetch_json)
    q = gitclaim.load_queue(home)
    assert not any(
        str(r.get("task") or "").upper() == "FIX" and str(r.get("id") or "") == "#3871"
        for r in (q.get("unaccepted") or []) + (q.get("accepted") or [])
    )
