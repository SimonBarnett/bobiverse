"""FR #4857: when main is red on test-and-synth, queue one main-side FIX."""
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

MAIN_SHA = "a" * 40
TIP_SHA = "b" * 40
REPO = "SimonBarnett/a-search"


def _pr(n: int, *, sha: str = TIP_SHA, checks: str = "failure:test-and-synth"):
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
            pass_sha=TIP_SHA,
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


def test_enqueue_shared_suite_main_red_queues_one_main_fix(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    first = mrb_merge_on_green.enqueue_fix_ci(
        home,
        repo=REPO,
        pr="4489",
        pass_sha=TIP_SHA,
        detail="failure:test-and-synth",
        main_red=True,
        main_sha=MAIN_SHA,
        now_epoch=1_000.0,
    )
    second = mrb_merge_on_green.enqueue_fix_ci(
        home,
        repo=REPO,
        pr="4478",
        pass_sha=TIP_SHA,
        detail="failure:test-and-synth",
        main_red=True,
        main_sha=MAIN_SHA,
        now_epoch=1_060.0,
    )
    assert first == "skipped_main_added"
    assert second == "skipped_main_duplicate"
    q = gitclaim.load_queue(home)
    fixes = [
        r
        for r in (q.get("unaccepted") or [])
        if isinstance(r, dict) and str(r.get("task") or "").upper() == "FIX"
    ]
    assert len(fixes) == 1
    row = fixes[0]
    assert str(row.get("id") or "").lstrip("#") == "main"
    assert "main-red|" in str(row.get("fail_signature") or "")
    assert MAIN_SHA[:12] in str(row.get("title") or "")
    tip_ids = {str(r.get("id") or "").lstrip("#") for r in fixes}
    assert "4489" not in tip_ids
    assert "4478" not in tip_ids


def test_resync_three_tips_main_red_one_main_fix(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setattr(
        mrb_merge_on_green, "main_branch_checks_red", lambda *_a, **_k: True
    )
    monkeypatch.setattr(
        mrb_merge_on_green, "main_branch_head_sha", lambda *_a, **_k: MAIN_SHA
    )
    prs = ["4489", "4478", "4491"]
    _seed_passes(tmp_path, prs)
    res = gitclaim.resync_from_github(
        tmp_path,
        [REPO],
        fetch_json=_fetch([_pr(int(n)) for n in prs]),
    )
    assert res.get("ok") is True
    assert int(res.get("added") or 0) == 1
    assert int(res.get("fix_skip_main_red") or 0) == 3
    rows = gitclaim.load_unaccepted(tmp_path)
    fixes = [
        r
        for r in rows
        if isinstance(r, dict) and str(r.get("task") or "").upper() == "FIX"
    ]
    assert len(fixes) == 1
    assert str(fixes[0].get("id") or "").lstrip("#") == "main"
    out = capsys.readouterr().out
    assert "result=skipped_main_added" in out
    assert out.count("result=skipped_main_duplicate") == 2

    again = gitclaim.resync_from_github(
        tmp_path,
        [REPO],
        fetch_json=_fetch([_pr(int(n)) for n in prs]),
    )
    assert int(again.get("added") or 0) == 0
    assert int(again.get("fix_skip_main_red") or 0) == 3
    fixes2 = [
        r
        for r in gitclaim.load_unaccepted(tmp_path)
        if isinstance(r, dict) and str(r.get("task") or "").upper() == "FIX"
    ]
    assert len(fixes2) == 1


def test_resync_after_main_green_offers_tip_fix(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    state = {"red": True}

    def main_red(*_a, **_k):
        return bool(state["red"])

    monkeypatch.setattr(mrb_merge_on_green, "main_branch_checks_red", main_red)
    monkeypatch.setattr(
        mrb_merge_on_green, "main_branch_head_sha", lambda *_a, **_k: MAIN_SHA
    )
    _seed_passes(tmp_path, ["4489"])
    res1 = gitclaim.resync_from_github(
        tmp_path,
        [REPO],
        fetch_json=_fetch([_pr(4489)]),
    )
    assert int(res1.get("fix_skip_main_red") or 0) == 1
    state["red"] = False
    # Clear the main-side FIX so tip FIX can be offered cleanly.
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [], "done": gitclaim.load_queue(tmp_path).get("done") or []},
    )
    res2 = gitclaim.resync_from_github(
        tmp_path,
        [REPO],
        fetch_json=_fetch([_pr(4489)]),
    )
    assert int(res2.get("fix_skip_main_red") or 0) == 0
    fixes = [
        r
        for r in gitclaim.load_unaccepted(tmp_path)
        if isinstance(r, dict) and str(r.get("task") or "").upper() == "FIX"
    ]
    assert len(fixes) == 1
    assert str(fixes[0].get("id") or "").lstrip("#") == "4489"


def test_github_resync_ok_line_names_fix_skip_main_red():
    text = (ROOT / "common" / "scripts" / "chair_health.py").read_text(encoding="utf-8")
    assert "fix_skip_main_red={res.get('fix_skip_main_red', 0)}" in text


def test_main_red_fix_not_purged_as_dead_pull():
    row = {
        "task": "FIX",
        "repo": REPO,
        "id": "#main",
        "fail_signature": f"main-red|{REPO}|{MAIN_SHA}|test-and-synth",
        "main_red_fix": "1",
        "url": f"https://github.com/{REPO}/commit/{MAIN_SHA}",
    }
    assert (
        gitclaim._fix_is_dead(
            row,
            open_pulls={REPO: {"4489"}},
            fetched_repos={REPO},
        )
        is False
    )


def test_resolve_assign_url_keeps_main_red_commit_url():
    url = f"https://github.com/{REPO}/commit/{MAIN_SHA}"
    row = {
        "task": "FIX",
        "repo": REPO,
        "id": "#main",
        "url": url,
        "main_red_fix": "1",
    }
    assert gitclaim.resolve_assign_url(row) == url
