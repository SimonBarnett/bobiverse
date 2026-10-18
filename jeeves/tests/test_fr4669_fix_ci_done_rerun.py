"""FR #4669: DONE FIX with an unchanged head is not a permanent duplicate."""
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

SHA = "e" * 40
REPO = "SimonBarnett/a-search"


def _home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    return home


def _finish_fix(home: Path, nick: str = "flamingo-30252") -> None:
    q = gitclaim.load_queue(home)
    done = []
    for row in q.get("unaccepted") or []:
        if str(row.get("task") or "").upper() != "FIX":
            continue
        row["nick"] = nick
        row["done_by"] = nick
        row["result"] = "DONE"
        done.append(row)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [], "done": done},
    )


def test_done_fix_same_sha_updates_branch_then_reoffers(tmp_path, monkeypatch):
    home = _home(tmp_path)
    calls: list[tuple[str, str]] = []

    def fake_json(url, *, token, method="GET", body=None):
        calls.append((method, url))
        return {}

    monkeypatch.setattr(mrb_merge_on_green, "_gh_json", fake_json)
    first = mrb_merge_on_green.enqueue_fix_ci(
        home,
        repo=REPO,
        pr="3871",
        pass_sha=SHA,
        detail="failure:test-and-synth",
        main_red=False,
        token="FAKE_TOKEN",
    )
    assert first == "added"
    _finish_fix(home)
    second = mrb_merge_on_green.enqueue_fix_ci(
        home,
        repo=REPO,
        pr="3871",
        pass_sha=SHA,
        detail="failure:test-and-synth",
        main_red=False,
        token="FAKE_TOKEN",
    )
    assert second == "updated-branch"
    assert second != "duplicate"
    assert len(calls) == 1
    assert calls[0][0] == "PUT"
    assert calls[0][1].endswith("/pulls/3871/update-branch")
    third = mrb_merge_on_green.enqueue_fix_ci(
        home,
        repo=REPO,
        pr="3871",
        pass_sha=SHA,
        detail="failure:test-and-synth",
        main_red=False,
        token="FAKE_TOKEN",
    )
    assert third == "added"
    live = [
        r
        for r in gitclaim.load_queue(home).get("unaccepted") or []
        if str(r.get("task") or "").upper() == "FIX"
    ]
    assert len(live) == 1
    assert "flamingo-30252" in str(live[0].get("giveup_seats") or "")


def test_dirty_automerge_pr_is_offered_as_fix(tmp_path, monkeypatch):
    home = _home(tmp_path)
    monkeypatch.setattr(
        mrb_merge_on_green, "main_branch_checks_red", lambda *_a, **_k: False
    )
    mrb_merge_on_green.enqueue(
        home,
        repo=REPO,
        pr="3354",
        pass_sha=SHA,
        url=f"https://github.com/{REPO}/pull/3354",
    )
    # A finished FIX-CI must not hide the conflict.
    mrb_merge_on_green.enqueue_fix_ci(
        home,
        repo=REPO,
        pr="3354",
        pass_sha=SHA,
        detail="failure",
        main_red=False,
    )
    _finish_fix(home)
    pr = {
        "number": 3354,
        "title": "tip",
        "body": f"Closes {REPO}#1",
        "html_url": f"https://github.com/{REPO}/pull/3354",
        "state": "open",
        "draft": False,
        "auto_merge": {"merge_method": "squash"},
        "head": {"sha": SHA},
        "user": {"login": "u"},
        "checks": "failure",
        "mergeable": "CONFLICTING",
        "mergeable_state": "DIRTY",
    }

    def fetch_json(url: str):
        if "/pulls" in url and "state=closed" not in url:
            return [pr]
        if "/issues" in url:
            return []
        return []

    gitclaim.resync_from_github(home, [REPO], fetch_json=fetch_json)
    live = [
        r
        for r in gitclaim.load_queue(home).get("unaccepted") or []
        if str(r.get("task") or "").upper() == "FIX"
    ]
    assert len(live) == 1
    blob = str(live[0].get("body") or "") + " " + str(live[0].get("title") or "")
    assert "conflict" in blob.lower()
