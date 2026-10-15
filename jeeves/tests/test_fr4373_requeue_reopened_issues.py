"""FR #4373: Jeeves requeues reopened issues (leave done, keep priority, no pin)."""
from __future__ import annotations

import bobreport
import gitclaim
import registered_machines


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare", "ionos", "flamingo"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    return tmp_path


def _done_fr(
    *,
    repo="SimonBarnett/bobiverse",
    ident="#4030",
    url="https://github.com/SimonBarnett/bobiverse/pull/4082",
    result="PASS",
    labels=None,
    require_machine="ionos",
):
    row = {
        "repo": repo,
        "task": "FR",
        "id": ident,
        "seq": 1,
        "ts": "2026-10-11T00:00:00Z",
        "line": "DONE FR",
        "url": url,
        "result": result,
        "done_ts": "2026-10-11T01:00:00Z",
        "nick": "marchhare-1",
    }
    if labels is not None:
        row["labels"] = list(labels)
    if require_machine:
        row["require_machine"] = require_machine
    return row


def test_webhook_reopened_moves_done_to_unaccepted(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [],
            "done": [
                _done_fr(
                    labels=["release-blocker", "feature-request"],
                    require_machine="ionos",
                )
            ],
        },
    )
    claim = gitclaim.GitClaim(
        repo="SimonBarnett/bobiverse",
        task="FR",
        id="#4030",
        event="issues",
        action="reopened",
        line="GIT issues reopened",
        title="airc shell default",
        body="reopened release blocker",
        labels=["release-blocker", "feature-request"],
        state="open",
        opened_by="SimonBarnett",
    )
    assert gitclaim.apply_queue_event(home, claim) in ("added", "updated", "duplicate")
    doc = gitclaim._load_queue_unlocked(home)
    assert not any(
        r.get("id") == "#4030" and r.get("task") == "FR" for r in (doc.get("done") or [])
    )
    rows = [r for r in doc["unaccepted"] if r.get("id") == "#4030" and r.get("task") == "FR"]
    assert len(rows) == 1
    row = rows[0]
    assert "release-blocker" in (row.get("labels") or [])
    assert not row.get("require_machine")  # never re-pin (esp. bobiverse→ionos)
    hist = row.get("history") or []
    assert any("reopened" in str(h).lower() for h in hist)
    assert any("webhook" in str(h).lower() for h in hist)


def test_resync_requeues_open_issue_stuck_in_done(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [],
            "done": [
                _done_fr(
                    ident="#3834",
                    url="https://github.com/SimonBarnett/bobiverse/pull/3840",
                    labels=["release-blocker"],
                    require_machine="ionos",
                )
            ],
        },
    )

    def fetch(url: str):
        if "/issues?" in url:
            return [
                {
                    "number": 3834,
                    "title": "wonderland control channel",
                    "body": "reopened",
                    "labels": [{"name": "release-blocker"}],
                    "state": "open",
                }
            ]
        if "/pulls?" in url:
            return []
        return []

    out = gitclaim.resync_from_github(home, ["SimonBarnett/bobiverse"], fetch_json=fetch)
    assert out.get("ok") is True or "added" in out or out.get("added", 0) >= 0
    doc = gitclaim._load_queue_unlocked(home)
    assert not any(
        r.get("id") == "#3834" and str(r.get("task") or "").upper() == "FR"
        for r in (doc.get("done") or [])
    )
    rows = [
        r
        for r in doc["unaccepted"]
        if r.get("id") == "#3834" and str(r.get("task") or "").upper() == "FR"
    ]
    assert len(rows) == 1
    assert "release-blocker" in (rows[0].get("labels") or [])
    assert not rows[0].get("require_machine")
    hist = rows[0].get("history") or []
    assert any("resync" in str(h).lower() or "rebuild" in str(h).lower() for h in hist)


def test_release_blocker_requeued_offered_before_plain(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["workers"] = {
        "21232": {"state": "idle", "nick": "marchhare-21232"}
    }
    bobreport.save_digest(home, digest)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/a-search",
                    "task": "FR",
                    "id": "#9",
                    "seq": 1,
                    "ts": "t",
                    "line": "plain",
                    "title": "plain work",
                    "labels": ["feature-request"],
                }
            ],
            "accepted": [],
            "done": [
                _done_fr(
                    ident="#3900",
                    url="https://github.com/SimonBarnett/bobiverse/pull/3907",
                    labels=["release-blocker"],
                    require_machine="",
                )
            ],
        },
    )
    claim = gitclaim.GitClaim(
        repo="SimonBarnett/bobiverse",
        task="FR",
        id="#3900",
        event="issues",
        action="reopened",
        line="GIT issues reopened",
        title="sasl heal",
        labels=["release-blocker"],
        state="open",
    )
    gitclaim.apply_queue_event(home, claim)
    ordered = gitclaim.ordered_unaccepted(home)
    assert ordered
    assert ordered[0].get("id") == "#3900"
    assert "release-blocker" in (ordered[0].get("labels") or [])


def test_repeated_reopen_and_resync_leave_one_entry(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [],
            "done": [_done_fr(ident="#4030", require_machine="ionos")],
        },
    )
    claim = gitclaim.GitClaim(
        repo="SimonBarnett/bobiverse",
        task="FR",
        id="#4030",
        event="issues",
        action="reopened",
        line="GIT issues reopened",
        title="shell",
        labels=["release-blocker"],
        state="open",
    )
    gitclaim.apply_queue_event(home, claim)
    gitclaim.apply_queue_event(home, claim)

    def fetch(url: str):
        if "/issues?" in url:
            return [
                {
                    "number": 4030,
                    "title": "shell",
                    "body": "x",
                    "labels": [{"name": "release-blocker"}],
                    "state": "open",
                }
            ]
        if "/pulls?" in url:
            return []
        return []

    gitclaim.resync_from_github(home, ["SimonBarnett/bobiverse"], fetch_json=fetch)
    doc = gitclaim._load_queue_unlocked(home)
    rows = [
        r
        for r in (doc.get("unaccepted") or [])
        if r.get("id") == "#4030" and str(r.get("task") or "").upper() == "FR"
    ]
    assert len(rows) == 1
    assert not any(
        r.get("id") == "#4030" and str(r.get("task") or "").upper() == "FR"
        for r in (doc.get("done") or [])
    )
    assert not any(
        r.get("id") == "#4030" and str(r.get("task") or "").upper() == "FR"
        for r in (doc.get("accepted") or [])
    )


def test_closed_issue_in_done_stays_after_resync(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [],
            "done": [
                _done_fr(
                    ident="#100",
                    url="https://github.com/SimonBarnett/bobiverse/pull/101",
                    labels=["feature-request"],
                    require_machine="",
                )
            ],
        },
    )

    def fetch(url: str):
        if "/issues?" in url:
            return []  # #100 closed — not in open list
        if "/pulls?" in url:
            return []
        return []

    gitclaim.resync_from_github(home, ["SimonBarnett/bobiverse"], fetch_json=fetch)
    doc = gitclaim._load_queue_unlocked(home)
    assert any(
        r.get("id") == "#100" and str(r.get("task") or "").upper() == "FR"
        for r in (doc.get("done") or [])
    )
    assert not any(r.get("id") == "#100" for r in (doc.get("unaccepted") or []))
