"""FR #4594: resync must not skip ci-wait when required CI already concluded FAILURE.

PASSed + auto-merge + same SHA with completed/failure queues a FIX (not MRB).
in_progress / queued still skips as ci-wait.
"""
from __future__ import annotations

import gitclaim
import mrb_merge_on_green

SHA = "c" * 40
REPO = "SimonBarnett/a-search"


def _pr(n: int, *, sha: str = SHA, auto_merge: dict | None = None, checks: str | None = None):
    pr = {
        "number": n,
        "title": "fix: x",
        "body": f"Closes {REPO}#50",
        "html_url": f"https://github.com/{REPO}/pull/{n}",
        "state": "open",
        "draft": False,
        "auto_merge": auto_merge if auto_merge is not None else {"merge_method": "merge"},
        "head": {"sha": sha},
        "user": {"login": "u"},
    }
    if checks is not None:
        pr["checks"] = checks
    return pr


def _fetch(prs):
    def fetch_json(url: str):
        if "/pulls" in url and "state=closed" not in url:
            return list(prs)
        if "/issues" in url:
            return []
        return []

    return fetch_json


def _seed_pass(tmp_path, pr: str = "1796"):
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
            ],
        },
    )


def test_open_pr_waiting_on_ci_false_when_checks_failure():
    pr = _pr(1796, checks="failure")
    assert gitclaim.open_pr_mrb_waiting_on_ci(pr, SHA, checks="failure") is False
    assert gitclaim.open_pr_mrb_waiting_on_ci(pr, SHA, checks="completed/failure") is False


def test_open_pr_waiting_on_ci_true_when_checks_pending():
    pr = _pr(1796, checks="in_progress")
    assert gitclaim.open_pr_mrb_waiting_on_ci(pr, SHA, checks="in_progress") is True
    assert gitclaim.open_pr_mrb_waiting_on_ci(pr, SHA, checks="queued") is True
    assert gitclaim.open_pr_mrb_waiting_on_ci(pr, SHA, checks="pending") is True


def test_resync_ci_failed_queues_fix_not_mrb(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _seed_pass(tmp_path)
    res = gitclaim.resync_from_github(
        tmp_path,
        [REPO],
        fetch_json=_fetch([_pr(1796, checks="failure")]),
    )
    assert res.get("ok") is True
    rows = gitclaim.load_unaccepted(tmp_path)
    fixes = [r for r in rows if str(r.get("task") or "").upper() == "FIX"]
    mrbs = [
        r
        for r in rows
        if str(r.get("task") or "").upper() == "MRB" and str(r.get("id") or "") == "#1796"
    ]
    assert len(fixes) == 1, f"expected one FIX, got {rows!r}"
    assert fixes[0].get("id") in ("#1796", "1796")
    assert mrbs == []
    out = capsys.readouterr().out
    assert not any("skip ci-wait PR" in line and "1796" in line for line in out.splitlines())
    assert any(
        "resync offer FIX ci-failed PR" in line and "1796" in line
        for line in out.splitlines()
    )


def test_resync_in_progress_still_skips_ci_wait(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _seed_pass(tmp_path, pr="2183")
    res = gitclaim.resync_from_github(
        tmp_path,
        [REPO],
        fetch_json=_fetch([_pr(2183, checks="in_progress")]),
    )
    assert res.get("ok") is True
    rows = gitclaim.load_unaccepted(tmp_path)
    assert not any(
        str(r.get("task") or "").upper() == "MRB" and str(r.get("id") or "") == "#2183"
        for r in rows
    )
    assert not any(
        str(r.get("task") or "").upper() == "FIX" and str(r.get("id") or "") in ("#2183", "2183")
        for r in rows
    )
    out = capsys.readouterr().out
    assert any("skip ci-wait PR" in line and "2183" in line for line in out.splitlines())
