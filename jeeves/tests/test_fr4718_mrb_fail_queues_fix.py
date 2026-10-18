"""FR #4718: MRB FAIL at the current head queues FIX, not another MRB."""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim
import mrb_merge_on_green
import shop_listen

REPO = "SimonBarnett/a-search"
SHA = "2619280f8712080d551647cb8b89aea46f3dbb45"
SEAT = "flamingo-33384"
OTHER = "flamingo-30252"


def _pr(n: int, *, sha: str = SHA, comments=None, title: str = "fix: x", checks: str = "success"):
    pr = {
        "number": n,
        "title": title,
        "body": f"Closes {REPO}#4318",
        "html_url": f"https://github.com/{REPO}/pull/{n}",
        "state": "open",
        "draft": False,
        "head": {"sha": sha},
        "user": {"login": "u"},
        "checks": checks,
        "mergeable": True,
        "mergeable_state": "clean",
    }
    if comments is not None:
        pr["comments"] = comments
    return pr


def _fail_comment():
    return [{"created_at": "2026-10-18T18:00:00Z", "body": f"MRB FAIL @ {SHA}"}]


def _fetch(prs):
    def fetch_json(url: str):
        if "/pulls" in url and "state=closed" not in url and "/comments" not in url:
            return list(prs)
        if "/issues" in url:
            return []
        return []

    return fetch_json


def test_newest_board_fail_beats_older_pass():
    comments = [
        {"created_at": "2026-10-18T17:00:00Z", "body": f"MRB PASS @ {SHA}"},
        {"created_at": "2026-10-18T18:00:00Z", "body": f"MRB FAIL @ {SHA}"},
    ]
    assert mrb_merge_on_green.newest_mrb_board(comments) == ("FAIL", SHA)


def test_resync_fail_board_queues_fix_not_mrb(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": REPO,
                    "task": "MRB",
                    "id": "#4319",
                    "url": f"https://github.com/{REPO}/pull/4319",
                    "title": "old mrb",
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    res = gitclaim.resync_from_github(
        tmp_path,
        [REPO],
        fetch_json=_fetch([_pr(4319, comments=_fail_comment())]),
    )
    assert res.get("ok") is True
    rows = gitclaim.load_unaccepted(tmp_path)
    fixes = [r for r in rows if str(r.get("task") or "").upper() == "FIX"]
    mrbs = [r for r in rows if str(r.get("task") or "").upper() == "MRB"]
    assert len(fixes) == 1
    assert fixes[0].get("id") in ("#4319", "4319")
    assert "MRB FAIL" in str(fixes[0].get("title") or "")
    assert mrbs == []
    out = capsys.readouterr().out
    assert "resync offer FIX mrb-fail PR" in out
    assert "4319" in out


def test_resync_linked_fix_pr_does_not_queue_another_fix(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    prs = [
        _pr(4319, comments=_fail_comment()),
        _pr(4400, title="fix(mrb-4319): keep market on the retry write"),
    ]
    res = gitclaim.resync_from_github(tmp_path, [REPO], fetch_json=_fetch(prs))
    assert res.get("ok") is True
    rows = gitclaim.load_unaccepted(tmp_path)
    assert not any(
        str(r.get("task") or "").upper() == "FIX" and str(r.get("id") or "") in ("#4319", "4319")
        for r in rows
    )
    assert not any(
        str(r.get("task") or "").upper() == "MRB" and str(r.get("id") or "") in ("#4319", "4319")
        for r in rows
    )


def test_resync_ledger_stamp_without_comments(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim.stamp_mrb_fail(tmp_path, REPO, "#4319", SHA, SEAT)
    res = gitclaim.resync_from_github(
        tmp_path,
        [REPO],
        fetch_json=_fetch([_pr(4319)]),
    )
    assert res.get("ok") is True
    rows = gitclaim.load_unaccepted(tmp_path)
    fixes = [r for r in rows if str(r.get("task") or "").upper() == "FIX"]
    assert len(fixes) == 1
    assert str(fixes[0].get("mrb_fail_by") or "") == SEAT
    assert not any(str(r.get("task") or "").upper() == "MRB" for r in rows)


def test_done_fail_queues_fix(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    (tmp_path / "registered-machines.json").write_text(
        '{"v":1,"machines":["flamingo"]}', encoding="utf-8"
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    doc = bobreport.empty_digest()
    doc["machines"]["flamingo"] = {
        "id": "flamingo",
        "online": True,
        "working_on": "",
        "worker_list": [{"nick": SEAT, "state": "idle", "work": ""}],
        "workers": {"33384": {"pid": "33384", "nick": SEAT, "state": "idle"}},
    }
    bobreport.save_digest(tmp_path, doc)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [
                {
                    "repo": REPO,
                    "task": "MRB",
                    "id": "#4319",
                    "url": f"https://github.com/{REPO}/pull/4319",
                    "nick": SEAT,
                }
            ],
            "done": [],
        },
    )
    monkeypatch.setattr(mrb_merge_on_green, "head_sha_for_mrb_fail", lambda repo, num: SHA)
    result = shop_listen.handle_shop_worker_line(
        tmp_path,
        nick=SEAT,
        channel="#flamingo",
        body=f"DONE MRB {REPO}#4319 FAIL https://github.com/{REPO}/pull/4319",
        post_fn=lambda _p: 204,
    )
    assert result.get("status") == "ok"
    assert result.get("mrb_fail_fix") == "added"
    rows = gitclaim.load_unaccepted(tmp_path)
    assert any(str(r.get("task") or "").upper() == "FIX" for r in rows)
    rec = gitclaim.mrb_fail_record(tmp_path, REPO, "#4319")
    assert rec and rec.get("sha") == SHA and rec.get("nick") == SEAT


def _register(home: Path, monkeypatch, nick: str) -> None:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    machine = nick.split("-", 1)[0]
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["' + machine + '"]}', encoding="utf-8"
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    doc = bobreport.empty_digest()
    doc["machines"][machine] = {
        "id": machine,
        "online": True,
        "working_on": "",
        "worker_list": [
            {"nick": SEAT, "state": "idle", "work": ""},
            {"nick": OTHER, "state": "idle", "work": ""},
        ],
        "workers": {
            "33384": {"pid": "33384", "nick": SEAT, "state": "idle"},
            "30252": {"pid": "30252", "nick": OTHER, "state": "idle"},
        },
    }
    bobreport.save_digest(home, doc)


def test_assign_fix_accepts_green_pr_with_fail_board(tmp_path, monkeypatch):
    _register(tmp_path, monkeypatch, OTHER)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [], "done": []},
    )
    monkeypatch.setattr(gitclaim, "worker_working_on", lambda h, n: "")
    monkeypatch.setattr(gitclaim, "live_seat_nicks", lambda h: {SEAT, OTHER})
    monkeypatch.setattr(gitclaim, "free_seat_nicks", lambda h, live: {SEAT, OTHER})
    monkeypatch.setattr(gitclaim, "seat_open_job", lambda *a, **k: "")

    def fake_fetch(repo, num):
        return {
            "number": 4319,
            "title": "keep market off keywords",
            "body": "Closes SimonBarnett/a-search#4318",
            "state": "open",
            "draft": False,
            "html_url": f"https://github.com/{REPO}/pull/4319",
            "pull_request": {"url": "https://api.github.com/repos/x"},
            "head": {"sha": SHA},
            "checks": "success",
            "comments": _fail_comment(),
            "labels": [],
        }

    st, job = gitclaim.assign_row(
        tmp_path,
        OTHER,
        REPO,
        "FIX",
        "#4319",
        fetch_issue=fake_fetch,
    )
    assert st == "ok", job
    assert str(job.get("task") or "").upper() == "FIX"


def test_assign_mrb_refuses_the_seat_that_failed_it(tmp_path, monkeypatch):
    _register(tmp_path, monkeypatch, SEAT)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": REPO,
                    "task": "MRB",
                    "id": "#4319",
                    "url": f"https://github.com/{REPO}/pull/4319",
                    "title": "keep market off keywords",
                    "mrb_fail_by": SEAT,
                    "pass_sha": SHA,
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    monkeypatch.setattr(gitclaim, "worker_working_on", lambda h, n: "")
    monkeypatch.setattr(gitclaim, "live_seat_nicks", lambda h: {SEAT, OTHER})
    monkeypatch.setattr(gitclaim, "free_seat_nicks", lambda h, live: {SEAT, OTHER})
    monkeypatch.setattr(gitclaim, "seat_open_job", lambda *a, **k: "")
    st, why = gitclaim.assign_row(tmp_path, SEAT, REPO, "MRB", "#4319")
    assert st == "refused"
    assert "FAILed" in str(why)
    assert gitclaim.mrb_fail_same_head_for_seat(
        {"task": "MRB", "mrb_fail_by": SEAT}, SEAT
    )
    assert not gitclaim.mrb_fail_same_head_for_seat(
        {"task": "MRB", "mrb_fail_by": SEAT}, OTHER
    )
