"""FR #4596: per-PR FIX when main is green; shared collapse only when main is red."""
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

SHA = "d" * 40
REPO = "SimonBarnett/a-search"


def _pr(n: int, *, sha: str = SHA, checks: str = "failure"):
    return {
        "number": n,
        "title": f"fix: tip {n}",
        "body": f"Closes {REPO}#50",
        "html_url": f"https://github.com/{REPO}/pull/{n}",
        "state": "open",
        "draft": False,
        "auto_merge": {"merge_method": "merge"},
        "head": {"sha": sha},
        "user": {"login": "u"},
        "checks": checks,
    }


def _fetch(prs):
    def fetch_json(url: str):
        if "/pulls" in url and "state=closed" not in url:
            return list(prs)
        if "/issues" in url:
            return []
        return []

    return fetch_json


def _seed_passes(tmp_path, prs: list[str]):
    for pr in prs:
        mrb_merge_on_green.enqueue(
            tmp_path,
            repo=REPO,
            pr=pr,
            pass_sha=SHA,
            url=f"https://github.com/{REPO}/pull/{pr}",
        )
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [],
            "done": [
                {
                    "repo": REPO,
                    "task": "MRB",
                    "id": f"#{pr}",
                    "result": "PASS",
                    "url": f"https://github.com/{REPO}/pull/{pr}",
                }
                for pr in prs
            ],
        },
    )


def test_failure_signature_per_pr_when_main_green():
    a = mrb_merge_on_green.failure_signature(
        REPO, detail="failure", pr="3641", main_red=False
    )
    b = mrb_merge_on_green.failure_signature(
        REPO, detail="failure", pr="3582", main_red=False
    )
    assert a != b
    assert "#3641" in a
    assert "#3582" in b


def test_failure_signature_shared_when_main_red():
    a = mrb_merge_on_green.failure_signature(
        REPO, detail="failure", pr="3641", main_red=True
    )
    b = mrb_merge_on_green.failure_signature(
        REPO, detail="failure", pr="3582", main_red=True
    )
    assert a == b
    assert "3641" not in a
    assert "3582" not in a


def test_resync_three_red_prs_main_green_adds_three_fix(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setattr(
        mrb_merge_on_green, "main_branch_checks_red", lambda *_a, **_k: False
    )
    prs = ["3641", "3582", "1796"]
    _seed_passes(tmp_path, prs)
    res = gitclaim.resync_from_github(
        tmp_path,
        [REPO],
        fetch_json=_fetch([_pr(int(n)) for n in prs]),
    )
    assert res.get("ok") is True
    assert int(res.get("added") or 0) >= 3
    rows = gitclaim.load_unaccepted(tmp_path)
    fixes = [
        r
        for r in rows
        if isinstance(r, dict) and str(r.get("task") or "").upper() == "FIX"
    ]
    assert len(fixes) == 3
    ids = {str(r.get("id") or "").lstrip("#") for r in fixes}
    assert ids == set(prs)
    out = capsys.readouterr().out
    added_lines = [
        ln for ln in out.splitlines() if "resync offer FIX" in ln and "result=added" in ln
    ]
    assert len(added_lines) == 3


def test_resync_three_red_prs_main_red_one_fix(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setattr(
        mrb_merge_on_green, "main_branch_checks_red", lambda *_a, **_k: True
    )
    prs = ["3641", "3582", "1796"]
    _seed_passes(tmp_path, prs)
    res = gitclaim.resync_from_github(
        tmp_path,
        [REPO],
        fetch_json=_fetch([_pr(int(n)) for n in prs]),
    )
    assert res.get("ok") is True
    assert int(res.get("added") or 0) == 1
    rows = gitclaim.load_unaccepted(tmp_path)
    fixes = [
        r
        for r in rows
        if isinstance(r, dict) and str(r.get("task") or "").upper() == "FIX"
    ]
    assert len(fixes) == 1
    out = capsys.readouterr().out
    assert sum(1 for ln in out.splitlines() if "result=added" in ln) == 1
    assert sum(1 for ln in out.splitlines() if "result=duplicate" in ln) == 2


def test_enqueue_main_green_two_prs_two_fix(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    a = mrb_merge_on_green.enqueue_fix_ci(
        home,
        repo=REPO,
        pr="3641",
        pass_sha=SHA,
        detail="failure",
        main_red=False,
        now_epoch=1_000.0,
    )
    b = mrb_merge_on_green.enqueue_fix_ci(
        home,
        repo=REPO,
        pr="3582",
        pass_sha=SHA,
        detail="failure",
        main_red=False,
        now_epoch=1_060.0,
    )
    assert a == "added"
    assert b == "added"
    q = gitclaim.load_queue(home)
    fixes = [
        r
        for r in (q.get("unaccepted") or [])
        if isinstance(r, dict) and str(r.get("task") or "").upper() == "FIX"
    ]
    assert len(fixes) == 2


def test_enqueue_main_red_two_prs_one_fix(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    a = mrb_merge_on_green.enqueue_fix_ci(
        home,
        repo=REPO,
        pr="3641",
        pass_sha=SHA,
        detail="failure",
        main_red=True,
        now_epoch=1_000.0,
    )
    b = mrb_merge_on_green.enqueue_fix_ci(
        home,
        repo=REPO,
        pr="3582",
        pass_sha=SHA,
        detail="failure",
        main_red=True,
        now_epoch=1_060.0,
    )
    assert a == "added"
    assert b == "duplicate"
    q = gitclaim.load_queue(home)
    fixes = [
        r
        for r in (q.get("unaccepted") or [])
        if isinstance(r, dict) and str(r.get("task") or "").upper() == "FIX"
    ]
    assert len(fixes) == 1
