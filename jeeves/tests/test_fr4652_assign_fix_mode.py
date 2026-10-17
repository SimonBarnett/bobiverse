"""FR #4652: !assign accepts FIX; enqueue open red PR from GitHub when missing."""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim

REPO = "SimonBarnett/a-search"
NICK = "marchhare-23068"


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
        "workers": {"23068": {"pid": "23068", "nick": NICK, "state": "idle"}},
    }
    bobreport.save_digest(home, doc)


def test_parse_assign_cmd_accepts_fix():
    assert gitclaim.parse_assign_cmd(
        f"!assign {NICK} {REPO} FIX 3582"
    ) == (NICK, REPO, "FIX", "#3582")
    assert gitclaim.parse_assign_cmd("!assign a b fix #9") == ("a", "b", "FIX", "#9")
    assert gitclaim.parse_assign_cmd("!assign a b XYZ 5") is None


def test_assign_fix_enqueues_red_pr_and_offers(tmp_path: Path, monkeypatch):
    _register(tmp_path, monkeypatch)
    _queue(tmp_path, unaccepted=[])
    monkeypatch.setattr(gitclaim, "worker_working_on", lambda h, n: "")
    monkeypatch.setattr(gitclaim, "live_seat_nicks", lambda h: {NICK})
    monkeypatch.setattr(gitclaim, "free_seat_nicks", lambda h, live: {NICK})
    monkeypatch.setattr(gitclaim, "seat_open_job", lambda *a, **k: "")

    sha = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

    def fake_fetch(repo, num):
        assert str(num).lstrip("#") == "3582"
        return {
            "number": 3582,
            "title": "lesson tip",
            "body": "x",
            "state": "open",
            "draft": False,
            "html_url": f"https://github.com/{REPO}/pull/3582",
            "pull_request": {"url": "https://api.github.com/..."},
            "head": {"sha": sha},
            "checks": "failure",
            "labels": [],
        }

    st, job = gitclaim.assign_row(
        tmp_path,
        NICK,
        REPO,
        "FIX",
        "#3582",
        fetch_issue=fake_fetch,
    )
    assert st == "ok", job
    assert isinstance(job, dict)
    assert str(job.get("task")).upper() == "FIX"
    assert str(job.get("id")) == "#3582"
    assert str(job.get("offered_to")) == NICK
    line = gitclaim.format_assign_line(NICK, job)
    assert line.startswith(f"{NICK}: FIX {REPO}#3582")
    assert "/pull/3582" in line
    rows = gitclaim.load_unaccepted(tmp_path)
    assert any(
        str(r.get("task")).upper() == "FIX" and str(r.get("id")) == "#3582" for r in rows
    )


def test_assign_fix_refuses_busy_seat(tmp_path: Path, monkeypatch):
    _register(tmp_path, monkeypatch)
    _queue(
        tmp_path,
        unaccepted=[
            {
                "repo": REPO,
                "task": "FIX",
                "id": "#3582",
                "url": f"https://github.com/{REPO}/pull/3582",
                "title": "FIX CI",
                "body": "red",
                "pass_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            }
        ],
    )
    monkeypatch.setattr(gitclaim, "worker_working_on", lambda h, n: "doing FR x#1")
    monkeypatch.setattr(gitclaim, "live_seat_nicks", lambda h: {NICK})
    monkeypatch.setattr(gitclaim, "free_seat_nicks", lambda h, live: set())
    monkeypatch.setattr(gitclaim, "seat_open_job", lambda *a, **k: "")
    st, why = gitclaim.assign_row(tmp_path, NICK, REPO, "FIX", "#3582")
    assert st == "refused"
    assert "busy" in str(why).lower()


def test_assign_fix_refuses_needs_human_row(tmp_path: Path, monkeypatch):
    """FR #4652 acceptance: needs_human FIX row is refused on !assign with a clear reason.

    Note: FR/MRB !assign may still hand out needs_human (FR #4336). FIX follows the
    FR #4652 letter for this gate.
    """
    _register(tmp_path, monkeypatch)
    _queue(
        tmp_path,
        unaccepted=[
            {
                "repo": REPO,
                "task": "FIX",
                "id": "#3582",
                "url": f"https://github.com/{REPO}/pull/3582",
                "title": "FIX CI",
                "body": "red",
                "needs_human": True,
                "pass_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            }
        ],
    )
    monkeypatch.setattr(gitclaim, "worker_working_on", lambda h, n: "")
    monkeypatch.setattr(gitclaim, "live_seat_nicks", lambda h: {NICK})
    monkeypatch.setattr(gitclaim, "free_seat_nicks", lambda h, live: {NICK})
    monkeypatch.setattr(gitclaim, "seat_open_job", lambda *a, **k: "")
    st, why = gitclaim.assign_row(tmp_path, NICK, REPO, "FIX", "#3582")
    assert st == "refused"
    assert "needs_human" in str(why).lower() or "needs-human" in str(why).lower()