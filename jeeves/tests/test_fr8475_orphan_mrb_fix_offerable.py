"""FR #8475: orphan and main-base fix(mrb-N) stay offerable MRB rows."""
from __future__ import annotations

from pathlib import Path

import gitclaim


REPO = "SimonBarnett/priority-mcp"


def _home(tmp_path: Path) -> Path:
    h = tmp_path / "chair"
    h.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(h),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return h


def _pr(num: int, title: str, *, base: str = "") -> dict:
    row = {
        "number": num,
        "title": title,
        "body": "",
        "draft": False,
        "html_url": f"https://github.com/{REPO}/pull/{num}",
        "user": {"login": "SimonBarnett"},
    }
    if base:
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


def _mrb_ids(home: Path) -> list:
    return [
        r.get("id")
        for r in gitclaim.load_unaccepted(home)
        if str(r.get("task") or "").upper() == "MRB"
    ]


def test_orphan_main_base_survives_purge(tmp_path, capsys):
    home = _home(tmp_path)
    gitclaim.resync_from_github(
        home,
        [REPO],
        fetch_json=_fetch(
            [_pr(665, "fix(mrb-593): system-db trigger dictionary", base="main")]
        ),
    )
    assert _mrb_ids(home) == ["#665"]
    row = gitclaim.load_unaccepted(home)[0]
    assert row.get("mrb_fix_offer") == "1"
    assert gitclaim.mrb_row_not_offerable_reason(row) is None
    assert gitclaim.mrb_row_offerable(row) is True
    err = capsys.readouterr().out
    assert "resync queue orphan mrb-fix PR SimonBarnett/priority-mcp#665" in err
    assert "purge_dead_mrb" not in err


def test_stacked_parent_branch_still_skipped(tmp_path, capsys):
    home = _home(tmp_path)
    gitclaim.resync_from_github(
        home,
        [REPO],
        fetch_json=_fetch(
            [
                _pr(593, "FR #1: parent", base="main"),
                _pr(664, "fix(mrb-593): stacked", base="some-other-branch"),
            ]
        ),
    )
    assert _mrb_ids(home) == ["#593"]
    err = capsys.readouterr().out
    assert "resync skip mrb-fix PR SimonBarnett/priority-mcp#664" in err


def test_main_base_while_parent_open_is_offerable(tmp_path):
    home = _home(tmp_path)
    gitclaim.resync_from_github(
        home,
        [REPO],
        fetch_json=_fetch(
            [
                _pr(593, "FR #1: parent", base="main"),
                _pr(700, "fix(mrb-593): on main", base="main"),
                _pr(701, "fix(mrb-593): twin", base="main"),
            ]
        ),
    )
    assert _mrb_ids(home) == ["#593", "#700"]


def test_unstamped_fix_title_still_not_offerable():
    row = {
        "repo": REPO,
        "task": "MRB",
        "id": "#664",
        "title": "fix(mrb-378): never Get-Content",
        "url": f"https://github.com/{REPO}/pull/664",
    }
    assert gitclaim.mrb_row_not_offerable_reason(row) == "fix_pr_title"


def test_webhook_main_base_enqueues_stacked_does_not():
    opened = gitclaim.claim_from_payload(
        "pull_request",
        {
            "action": "opened",
            "repository": {"full_name": REPO},
            "pull_request": _pr(665, "fix(mrb-593): dictionary", base="main"),
        },
    )
    assert opened is not None and opened.mrb_fix_offer is True
    stacked = gitclaim.claim_from_payload(
        "pull_request",
        {
            "action": "opened",
            "repository": {"full_name": REPO},
            "pull_request": _pr(664, "fix(mrb-593): stacked", base="fr-593"),
        },
    )
    assert stacked is None
    closed_parent = gitclaim.claim_from_payload(
        "pull_request",
        {
            "action": "opened",
            "repository": {"full_name": REPO},
            "pull_request": _pr(664, "fix(mrb-378): orphan branch", base="fr-378"),
        },
        mrb_fix_parent_open=lambda repo, parent: False,
    )
    assert closed_parent is not None and closed_parent.mrb_fix_offer is True


def test_monitor_flags_main_base_orphan_not_stacked():
    prs = [
        _pr(8353, "FR #8348: enable Priority", base="main"),
        {"number": 7777, "title": "fix(mrb-999): x", "draft": False},
        _pr(665, "fix(mrb-593): dictionary", base="main"),
        _pr(701, "fix(mrb-593): twin", base="main"),
        _pr(593, "parent", base="main"),
    ]
    # 701's parent 593 is open, so only keeper 665 is expected among the fixes.
    # 665's parent is not in the list, so it is an orphan on main.
    missing = gitclaim.list_open_prs_missing_mrb(prs, {"unaccepted": [], "accepted": []}, repo=REPO)
    assert [m["number"] for m in missing] == [8353, 665, 593]
    assert gitclaim.open_pr_expects_mrb_or_fix_row(prs[1]) is False
