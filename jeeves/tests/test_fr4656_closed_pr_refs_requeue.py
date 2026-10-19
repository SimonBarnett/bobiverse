"""FR #4656: closed-unmerged PR Refs must not become phantom FR rows."""
from __future__ import annotations

import bobreport
import gitclaim
import registered_machines

REPO = "SimonBarnett/a-search"


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare", "flamingo"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    return tmp_path


def _checkers(monkeypatch, *, is_pull, issue_open):
    monkeypatch.setattr(
        gitclaim,
        "github_is_pull_checker",
        lambda **_k: (lambda _repo, _num: is_pull),
    )
    monkeypatch.setattr(
        gitclaim,
        "github_issue_open_checker",
        lambda **_k: (lambda _repo, _num: issue_open),
    )


def _done_fr(ident):
    return {
        "repo": REPO,
        "task": "FR",
        "id": ident,
        "seq": 1,
        "ts": "2026-10-16T00:00:00Z",
        "line": "DONE FR",
        "result": "PASS",
        "done_ts": "2026-10-16T01:00:00Z",
    }


def _close_pr(refs):
    return gitclaim.GitClaim(
        repo=REPO,
        task="MRB",
        id="#3471",
        event="pull_request",
        action="closed",
        line="GIT pull_request SimonBarnett/a-search closed #3471",
        title="docs/mrb-3015: pin CLOSED-parent re-offer harvest lesson",
        body="Refs SimonBarnett/a-search#3015",
        refs=tuple(refs),
        merged=False,
    )


def _fr_ids(doc):
    return [
        r.get("id")
        for r in (doc.get("unaccepted") or [])
        if str(r.get("task") or "").upper() == "FR"
    ]


def test_closed_unmerged_ref_that_is_a_pull_adds_no_fr(tmp_path, monkeypatch, capsys):
    home = _home(tmp_path, monkeypatch)
    _checkers(monkeypatch, is_pull=True, issue_open=False)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [_done_fr("#3015")]},
    )
    gitclaim.apply_queue_event(home, _close_pr(("#3015",)))
    doc = gitclaim._load_queue_unlocked(home)
    assert _fr_ids(doc) == []
    assert any(r.get("id") == "#3015" for r in doc.get("done") or [])
    err = capsys.readouterr().out
    assert "requeue skip ref #3015: pull request" in err


def test_closed_unmerged_ref_that_is_a_closed_issue_adds_no_fr(tmp_path, monkeypatch, capsys):
    home = _home(tmp_path, monkeypatch)
    _checkers(monkeypatch, is_pull=False, issue_open=False)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [_done_fr("#3016")]},
    )
    gitclaim.apply_queue_event(home, _close_pr(("#3016",)))
    doc = gitclaim._load_queue_unlocked(home)
    assert _fr_ids(doc) == []
    assert any(r.get("id") == "#3016" for r in doc.get("done") or [])
    err = capsys.readouterr().out
    assert "requeue skip ref #3016: issue closed" in err


def test_closed_unmerged_open_issue_in_done_still_requeues(tmp_path, monkeypatch, capsys):
    home = _home(tmp_path, monkeypatch)
    _checkers(monkeypatch, is_pull=False, issue_open=True)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [_done_fr("#3017")]},
    )
    gitclaim.apply_queue_event(home, _close_pr(("#3017",)))
    doc = gitclaim._load_queue_unlocked(home)
    assert _fr_ids(doc) == ["#3017"]
    assert not any(
        r.get("id") == "#3017" and str(r.get("task") or "").upper() == "FR"
        for r in (doc.get("done") or [])
    )
    err = capsys.readouterr().out
    assert "requeue skip ref" not in err


def test_resync_prunes_phantom_fr_for_closed_pr(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": REPO,
                    "task": "FR",
                    "id": "#3015",
                    "event": "issues",
                    "action": "reopened",
                    "line": "GIT pull_request SimonBarnett/a-search closed #3471",
                    "history": [
                        "reopened via=webhook by=unknown at=2026-10-17T23:42:49Z"
                    ],
                }
            ],
            "accepted": [],
            "done": [],
        },
    )

    def fetch(url: str):
        if "/issues?" in url or "/pulls?" in url:
            return []
        return []

    gitclaim.resync_from_github(home, [REPO], fetch_json=fetch)
    doc = gitclaim._load_queue_unlocked(home)
    assert _fr_ids(doc) == []
