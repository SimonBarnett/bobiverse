"""Hostile pins for FR #4422 / MRB #4423: LOST_DONE requeue; assign MRB enqueue."""
from __future__ import annotations

import time
from pathlib import Path

import bobreport
import gitclaim
import shop_listen

REPO = "SimonBarnett/bobiverse"
NICK = "marchhare-11732"


def _queue(home: Path, unaccepted=None, accepted=None, done=None) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": list(unaccepted or []),
            "accepted": list(accepted or []),
            "done": list(done or []),
        },
    )


def _register(home: Path, monkeypatch) -> None:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["marchhare"]}', encoding="utf-8"
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    doc = bobreport.empty_digest()
    doc["machines"]["marchhare"] = {
        "id": "marchhare",
        "online": True,
        "working_on": "",
        "worker_list": [{"nick": NICK, "state": "idle", "work": ""}],
        "workers": {"11732": {"pid": "11732", "nick": NICK, "state": "idle"}},
    }
    bobreport.save_digest(home, doc)


def test_mrb4423_lost_done_restart_requeues_without_pull(tmp_path: Path, monkeypatch):
    """Session-boundary heal must requeue, never invent done[], when digest has no /pull/."""
    _register(tmp_path, monkeypatch)
    now = time.time()
    session_started = now - 60
    old = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 300))
    _queue(
        tmp_path,
        accepted=[
            {
                "repo": REPO,
                "task": "FR",
                "id": "#4422",
                "nick": NICK,
                "accepted_ts": old,
                "ts": old,
            }
        ],
    )
    assert gitclaim.release_stale_busy(
        tmp_path, NICK, now, session_started=session_started
    )
    q = gitclaim.load_queue(tmp_path)
    assert q["accepted"] == []
    assert not any(str(r.get("id")) == "#4422" for r in (q.get("done") or []))
    assert any(
        str(r.get("id")) == "#4422"
        and "requeue:LOST_DONE_RESTART" in str(r.get("reconcile") or "")
        for r in (q.get("unaccepted") or [])
    )


def test_mrb4423_assign_enqueues_open_mrb_missing_from_queue(tmp_path: Path, monkeypatch):
    _register(tmp_path, monkeypatch)
    _queue(tmp_path, unaccepted=[])
    monkeypatch.setattr(gitclaim, "worker_working_on", lambda h, n: "")
    monkeypatch.setattr(gitclaim, "live_seat_nicks", lambda h: {NICK})
    monkeypatch.setattr(gitclaim, "free_seat_nicks", lambda h, live: {NICK})
    monkeypatch.setattr(gitclaim, "seat_open_job", lambda *a, **k: "")
    monkeypatch.setattr(
        gitclaim,
        "mrb_row_offerable",
        lambda *a, **k: True,
    )
    monkeypatch.setattr(gitclaim, "mrb_already_done", lambda *a, **k: False)
    monkeypatch.setattr(gitclaim, "review_blocked_for_author", lambda *a, **k: False)

    def fake_fetch(repo, num):
        assert str(num).lstrip("#") == "4423"
        return {
            "number": 4423,
            "title": "FR #4422 implement PR",
            "body": "Closes #4422",
            "state": "open",
            "labels": [],
            "pull_request": {"merged_at": None},
            "html_url": f"https://github.com/{repo}/pull/4423",
        }

    st, job = gitclaim.assign_row(
        tmp_path,
        NICK,
        REPO,
        "MRB",
        "#4423",
        fetch_issue=fake_fetch,
        pr_exists=lambda *a, **k: True,
    )
    assert st == "ok", job
    assert str(job.get("id")) == "#4423"
    assert "/pull/4423" in str(job.get("url") or "")
    rows = gitclaim.load_unaccepted(tmp_path)
    assert any(str(r.get("id")) == "#4423" and str(r.get("task")).upper() == "MRB" for r in rows)


def test_mrb4423_complete_fr_rejects_pass_without_pull_path(tmp_path: Path, monkeypatch):
    """DONE FR with PASS text but no /pull/ must stay refused (no invent-done)."""
    _register(tmp_path, monkeypatch)
    row = {
        "repo": REPO,
        "task": "FR",
        "id": "#4422",
        "nick": NICK,
        "accepted_ts": "2026-10-16T12:00:00Z",
    }
    _queue(tmp_path, accepted=[row])
    st, job = shop_listen.complete_job_by_ref(
        tmp_path, nick=NICK, repo=REPO, task="FR", ident="#4422", result="PASS", url=""
    )
    assert st == "refused"
    assert job is None
    assert len(gitclaim.load_queue(tmp_path)["accepted"]) == 1
