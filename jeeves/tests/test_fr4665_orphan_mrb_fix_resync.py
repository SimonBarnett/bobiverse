"""FR #4665: an open fix(mrb-N) PR is an MRB only after parent N is not open."""
from __future__ import annotations

from pathlib import Path

import gitclaim
import registered_machines


REPO = "SimonBarnett/a-search"


def _home(tmp_path: Path) -> Path:
    h = tmp_path / "chair"
    h.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(h),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return h


def _pr(num: int, title: str, body: str = "") -> dict:
    return {
        "number": num,
        "title": title,
        "body": body,
        "draft": False,
        "html_url": f"https://github.com/{REPO}/pull/{num}",
        "user": {"login": "SimonBarnett"},
    }


def _fetch(prs: list[dict]):
    def fetch(url: str):
        if "/pulls?" in url and "state=open" in url:
            return prs
        if "/issues?" in url:
            return []
        return []

    return fetch


def test_parent_id_shapes():
    assert gitclaim.mrb_fix_parent_pr_id("fix(mrb-3743): quote npm.cmd") == "#3743"
    assert gitclaim.mrb_fix_parent_pr_id("mrb-3743-fix: quote npm.cmd") == "#3743"
    assert gitclaim.mrb_fix_parent_pr_id("docs(mrb-229): note") == ""
    assert gitclaim.is_mrb_fix_pr_title("fix(mrb-3743): quote npm.cmd")


def test_open_parent_stays_skipped(tmp_path, capsys):
    home = _home(tmp_path)
    gitclaim.resync_from_github(
        home,
        [REPO],
        fetch_json=_fetch(
            [
                _pr(3743, "fix(#3663): runCdkSynth busy-wait"),
                _pr(3744, "fix(mrb-3743): quote Windows npm.cmd"),
            ]
        ),
    )
    ids = [
        r.get("id")
        for r in gitclaim.load_unaccepted(home)
        if str(r.get("task") or "").upper() == "MRB"
    ]
    assert ids == ["#3743"]
    err = capsys.readouterr().out
    assert "resync skip mrb-fix PR SimonBarnett/a-search#3744 parent #3743 still open" in err


def test_merged_parent_queues_mrb_and_stamps_author(tmp_path, capsys, monkeypatch):
    home = _home(tmp_path)
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    registered_machines.save_registered(home, {"marchhare"})
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [],
            "done": [
                {
                    "repo": REPO,
                    "task": "FR",
                    "id": "#3663",
                    "nick": "marchhare-21232",
                    "url": f"https://github.com/{REPO}/pull/3744",
                    "result": "DONE",
                }
            ],
            "workers": {},
        },
    )
    gitclaim.resync_from_github(
        home,
        [REPO],
        fetch_json=_fetch(
            [_pr(3744, "fix(mrb-3743): quote Windows npm.cmd under shell:true")]
        ),
    )
    rows = [
        r
        for r in gitclaim.load_unaccepted(home)
        if str(r.get("task") or "").upper() == "MRB"
    ]
    assert [r.get("id") for r in rows] == ["#3744"]
    assert "/pull/3744" in str(rows[0].get("url") or "")
    assert rows[0].get("author_seat") == "marchhare-21232"
    err = capsys.readouterr().out
    assert "resync queue orphan mrb-fix PR SimonBarnett/a-search#3744 parent #3743 not open" in err


def test_webhook_opened_mrb_fix_still_skipped():
    claim = gitclaim.claim_from_payload(
        "pull_request",
        {
            "action": "opened",
            "repository": {"full_name": REPO},
            "pull_request": {
                "number": 3744,
                "title": "fix(mrb-3743): quote Windows npm.cmd",
                "html_url": f"https://github.com/{REPO}/pull/3744",
                "body": "",
                "merged": False,
            },
        },
    )
    assert claim is None
