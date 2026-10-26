"""FR #4994: mrb-fix PRs that target main while parent is open must get an MRB.

Stacked fix(mrb-N) onto the parent branch still skips (FR #4665). Fixes that
land on the default branch (main/master) are reviewable alone --- skipping them
while treating the parent as FIX-linked deadlocks both sides (euroflo #11/#13/#16).
When several main-base twins exist for one parent, queue only the lowest number.
"""
from __future__ import annotations

from pathlib import Path

import gitclaim


REPO = "SimonBarnett/euroflo"


def _home(tmp_path: Path) -> Path:
    h = tmp_path / "chair"
    h.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(h),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return h


def _pr(num: int, title: str, *, base: str | None = None, body: str = "") -> dict:
    row = {
        "number": num,
        "title": title,
        "body": body,
        "draft": False,
        "html_url": f"https://github.com/{REPO}/pull/{num}",
        "user": {"login": "SimonBarnett"},
    }
    if base is not None:
        row["base"] = {"ref": base}
    return row


def _fetch(prs: list[dict]):
    def fetch(url: str):
        if "/pulls?" in url and "state=open" in url:
            return prs
        if "/issues?" in url:
            return []
        return []

    return fetch


def test_pr_base_ref_helper():
    assert gitclaim.pr_base_ref({"base": {"ref": "main"}}) == "main"
    assert gitclaim.pr_base_ref({"base": {"ref": "Master"}}) == "master"
    assert gitclaim.pr_base_ref({}) == ""
    assert gitclaim.mrb_fix_targets_default_branch({"base": {"ref": "main"}})
    assert gitclaim.mrb_fix_targets_default_branch({"base": {"ref": "master"}})
    assert not gitclaim.mrb_fix_targets_default_branch({"base": {"ref": "fix/mrb-11"}})
    assert not gitclaim.mrb_fix_targets_default_branch({})


def test_main_base_fix_queued_while_parent_open(tmp_path, capsys):
    home = _home(tmp_path)
    gitclaim.resync_from_github(
        home,
        [REPO],
        fetch_json=_fetch(
            [
                _pr(11, "harvest: session sweep"),
                _pr(13, "FIX(mrb-11): strip harvest BOM", base="main"),
            ]
        ),
    )
    ids = [
        r.get("id")
        for r in gitclaim.load_unaccepted(home)
        if str(r.get("task") or "").upper() == "MRB"
    ]
    assert "#13" in ids
    assert "#11" in ids  # parent still an ordinary MRB (no FAIL board in this fixture)
    err = capsys.readouterr().out
    assert "resync queue main-base mrb-fix PR SimonBarnett/euroflo#13 parent #11 still open" in err


def test_stacked_fix_still_skipped_while_parent_open(tmp_path, capsys):
    """Non-default base keeps FR #4665 skip (fix stacked on parent branch)."""
    home = _home(tmp_path)
    gitclaim.resync_from_github(
        home,
        [REPO],
        fetch_json=_fetch(
            [
                _pr(11, "harvest: session sweep", base="main"),
                _pr(13, "fix(mrb-11): strip BOM", base="harvest/session-branch"),
            ]
        ),
    )
    ids = [
        r.get("id")
        for r in gitclaim.load_unaccepted(home)
        if str(r.get("task") or "").upper() == "MRB"
    ]
    assert ids == ["#11"]
    err = capsys.readouterr().out
    assert "resync skip mrb-fix PR SimonBarnett/euroflo#13 parent #11 still open" in err


def test_twin_main_base_fixes_queue_lowest_only(tmp_path, capsys):
    home = _home(tmp_path)
    gitclaim.resync_from_github(
        home,
        [REPO],
        fetch_json=_fetch(
            [
                _pr(11, "harvest: session sweep", base="main"),
                _pr(16, "fix(mrb-11): strip BOM later twin", base="main"),
                _pr(13, "FIX(mrb-11): strip harvest BOM", base="main"),
            ]
        ),
    )
    ids = [
        r.get("id")
        for r in gitclaim.load_unaccepted(home)
        if str(r.get("task") or "").upper() == "MRB"
    ]
    assert "#13" in ids
    assert "#16" not in ids
    assert "#11" in ids
    err = capsys.readouterr().out
    assert "resync queue main-base mrb-fix PR SimonBarnett/euroflo#13 parent #11 still open" in err
    assert "resync skip twin mrb-fix PR SimonBarnett/euroflo#16 keeper #13" in err


def test_mrb_fail_linked_still_queues_main_base_fix(tmp_path, capsys, monkeypatch):
    """Parent FAIL+linked must not deadlock: main-base fix still becomes MRB."""
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [],
            "done": [
                {
                    "repo": REPO,
                    "task": "MRB",
                    "id": "#11",
                    "result": "FAIL",
                    "fail_signature": "mrb-fail|SimonBarnett/euroflo|11|abc",
                    "nick": "win-mpre8vi4u6u-14060",
                    "url": f"https://github.com/{REPO}/pull/11",
                }
            ],
            "workers": {},
        },
    )

    def fake_fail_board(pr, head_sha, ledger_rec=None):
        if str(pr.get("number")) == "11":
            return ("abc", "win-mpre8vi4u6u-14060")
        return ("", "")

    import mrb_merge_on_green as mog

    monkeypatch.setattr(mog, "mrb_fail_board_at_head", fake_fail_board)

    parent = _pr(11, "harvest: session sweep", base="main")
    parent["head"] = {"sha": "abc"}
    parent["comments"] = [
        {
            "body": "## MRB board\n**Verdict:** FAIL\n**MRB FAIL @ abc**\n",
            "user": {"login": "x"},
        }
    ]
    gitclaim.resync_from_github(
        home,
        [REPO],
        fetch_json=_fetch(
            [
                parent,
                _pr(13, "FIX(mrb-11): strip harvest BOM", base="main"),
            ]
        ),
    )
    ids = [
        r.get("id")
        for r in gitclaim.load_unaccepted(home)
        if str(r.get("task") or "").upper() == "MRB"
    ]
    assert ids == ["#13"]
    err = capsys.readouterr().out
    assert "resync offer FIX mrb-fail PR SimonBarnett/euroflo#11 result=linked" in err
    assert "resync queue main-base mrb-fix PR SimonBarnett/euroflo#13 parent #11 still open" in err
