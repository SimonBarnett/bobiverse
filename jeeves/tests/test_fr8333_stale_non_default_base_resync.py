"""FR #8333: open PRs with an explicit non-default base must not fake-land on main.

Class of bobiverse#8320 (fix(mrb-8316) base=fr-8310-land after that branch
merged): mergeStateStatus CLEAN but the tip can never reach main. Resync must
skip orphan mrb-fix rows with an explicit non-default base and warn on other
non-default open PRs.
"""
from __future__ import annotations

from pathlib import Path

import gitclaim


REPO = "SimonBarnett/bobiverse"


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


def test_helpers_explicit_non_default():
    assert gitclaim.pr_base_ref({"base": {"ref": "fr-8310-land"}}) == "fr-8310-land"
    assert gitclaim.pr_base_is_explicit_non_default({"base": {"ref": "fr-8310-land"}})
    assert gitclaim.pr_base_is_explicit_non_default({"base": {"ref": "Fix/mrb-11"}})
    assert not gitclaim.pr_base_is_explicit_non_default({"base": {"ref": "main"}})
    assert not gitclaim.pr_base_is_explicit_non_default({"base": {"ref": "Master"}})
    assert not gitclaim.pr_base_is_explicit_non_default({})
    assert not gitclaim.pr_base_is_explicit_non_default({"base": {}})
    rows = gitclaim.list_open_prs_explicit_non_default_base(
        [
            _pr(8320, "fix(mrb-8316): pins", base="fr-8310-land"),
            _pr(8332, "FR #8331: pins", base="main"),
            {**_pr(9, "wip", base="feature"), "draft": True},
        ]
    )
    assert [r["number"] for r in rows] == [8320]
    assert rows[0]["base"] == "fr-8310-land"


def test_orphan_mrb_fix_non_default_base_skipped(tmp_path, capsys):
    """#8320 class: parent gone, base still on merged fr-* tip -> skip."""
    home = _home(tmp_path)
    gitclaim.resync_from_github(
        home,
        [REPO],
        fetch_json=_fetch(
            [
                _pr(
                    8320,
                    "fix(mrb-8316): harvest hostile pins read SKILL.md + lessons.md archive",
                    base="fr-8310-land",
                )
            ]
        ),
    )
    ids = [
        r.get("id")
        for r in gitclaim.load_unaccepted(home)
        if str(r.get("task") or "").upper() == "MRB"
    ]
    assert "#8320" not in ids
    err = capsys.readouterr().out
    assert "resync skip orphan mrb-fix PR SimonBarnett/bobiverse#8320" in err
    assert "non-default base fr-8310-land" in err
    assert "FR #8333" in err


def test_orphan_mrb_fix_main_base_still_queues(tmp_path, capsys):
    home = _home(tmp_path)
    gitclaim.resync_from_github(
        home,
        [REPO],
        fetch_json=_fetch(
            [_pr(8320, "fix(mrb-8316): harvest pins", base="main")]
        ),
    )
    ids = [
        r.get("id")
        for r in gitclaim.load_unaccepted(home)
        if str(r.get("task") or "").upper() == "MRB"
    ]
    assert ids == ["#8320"]
    err = capsys.readouterr().out
    assert "resync queue orphan mrb-fix PR SimonBarnett/bobiverse#8320" in err


def test_orphan_mrb_fix_missing_base_still_queues(tmp_path, capsys):
    """Thin payloads / fixtures without base keep FR #4665 orphan queue."""
    home = _home(tmp_path)
    gitclaim.resync_from_github(
        home,
        [REPO],
        fetch_json=_fetch([_pr(3744, "fix(mrb-3743): quote npm.cmd")]),
    )
    ids = [
        r.get("id")
        for r in gitclaim.load_unaccepted(home)
        if str(r.get("task") or "").upper() == "MRB"
    ]
    assert ids == ["#3744"]
    err = capsys.readouterr().out
    assert "resync queue orphan mrb-fix" in err


def test_non_fix_non_default_base_warns_but_may_queue(tmp_path, capsys):
    home = _home(tmp_path)
    gitclaim.resync_from_github(
        home,
        [REPO],
        fetch_json=_fetch(
            [_pr(99, "experiment: stacked tip", base="feature/x")]
        ),
    )
    err = capsys.readouterr().out
    assert "resync warn non-default base PR SimonBarnett/bobiverse#99" in err
    assert "base=feature/x" in err
