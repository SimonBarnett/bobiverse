"""FR #3400: departed seat's ACKed row returns to unaccepted; !assign rules."""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim
import registered_machines as rm


MID = "marchhare"
GONE = "marchhare-14444"
LIVE = "marchhare-18212"
REPO = "SimonBarnett/a-search"


def _home(tmp_path: Path, monkeypatch) -> Path:
    h = tmp_path / "chair"
    h.mkdir()
    monkeypatch.setenv("BOB_DIGEST_HOME", str(h))
    monkeypatch.setenv("BOB_HOME", str(h))
    rm.sync_from_chanserv(h, ["#bobiverse", f"#{MID}"])
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    gitclaim._write_queue(
        gitclaim.queue_path(h),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    # Seed digest with machine entry.
    doc = bobreport.load_digest(h)
    doc.setdefault("machines", {})[MID] = {
        "shop": f"#{MID}",
        "worker_list": [],
        "workers": {},
    }
    bobreport.save_digest(h, doc)
    return h


def _accepted_row(**extra):
    row = {
        "task": "FR",
        "repo": REPO,
        "id": "#636",
        "title": "orphan",
        "url": f"https://github.com/{REPO}/issues/636",
        "state": "open",
        "nick": GONE,
        "accepted_by": GONE,
        "channel": f"#{MID}",
        "accepted_ts": "2026-10-08T10:39:42Z",
    }
    row.update(extra)
    return row


def test_release_accepted_for_departed_nick_returns_to_unaccepted(tmp_path, monkeypatch):
    h = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(h),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [_accepted_row()],
            "done": [],
        },
    )
    released = gitclaim.release_accepted_for_departed_nick(h, GONE)
    assert len(released) == 1
    assert released[0]["id"] == "#636"
    doc = gitclaim._load_queue_unlocked(h)
    assert doc["accepted"] == []
    assert len(doc["unaccepted"]) == 1
    row = doc["unaccepted"][0]
    assert row["id"] == "#636"
    assert row.get("nick") in ("", None) or "nick" not in row or not row.get("nick")
    assert not row.get("accepted_ts")
    assert row.get("retry") is True or "prior ACK void" in str(row.get("note") or "")
    assert "prior ACK void" in str(row.get("note") or row.get("retry_note") or "")


def test_release_does_not_steal_from_live_seat_when_nick_still_listed(tmp_path, monkeypatch):
    """release_accepted_for_departed_nick is only for departed nicks; live holder stays."""
    h = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(h),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [_accepted_row(nick=LIVE, accepted_by=LIVE)],
            "done": [],
        },
    )
    # Caller only invokes release for the departed nick; LIVE rows untouched.
    released = gitclaim.release_accepted_for_departed_nick(h, GONE)
    assert released == []
    doc = gitclaim._load_queue_unlocked(h)
    assert len(doc["accepted"]) == 1
    assert doc["accepted"][0]["nick"] == LIVE


def test_worker_remove_releases_accepted(tmp_path, monkeypatch):
    h = _home(tmp_path, monkeypatch)
    # Put gone nick on worker_list, then remove.
    doc = bobreport.load_digest(h)
    doc["machines"][MID]["worker_list"] = [
        {"nick": GONE, "state": "doing", "work": f"FR {REPO}#636", "updated": "2026-10-08T10:40:00Z"}
    ]
    bobreport.save_digest(h, doc)
    gitclaim._write_queue(
        gitclaim.queue_path(h),
        {"v": 1, "unaccepted": [], "accepted": [_accepted_row()], "done": []},
    )
    out = bobreport.apply_callback(
        h,
        {"op": "worker-remove", "machine": MID, "nick": GONE},
        "Jeeves",
    )
    assert out.ok
    q = gitclaim._load_queue_unlocked(h)
    assert q["accepted"] == []
    assert any(r.get("id") == "#636" for r in q["unaccepted"])


def test_assign_releases_orphan_accepted_and_offers(tmp_path, monkeypatch):
    h = _home(tmp_path, monkeypatch)
    doc = bobreport.load_digest(h)
    doc["machines"][MID]["worker_list"] = [
        {"nick": LIVE, "state": "idle", "work": "", "updated": "2026-10-08T12:00:00Z"}
    ]
    bobreport.save_digest(h, doc)
    gitclaim._write_queue(
        gitclaim.queue_path(h),
        {"v": 1, "unaccepted": [], "accepted": [_accepted_row()], "done": []},
    )
    # Gone nick not live; LIVE is live.
    status, job = gitclaim.assign_row(h, LIVE, REPO, "FR", "#636", issue_open=lambda *_: True)
    assert status == "ok", job
    assert isinstance(job, dict)
    assert job.get("offered_to") == LIVE
    q = gitclaim._load_queue_unlocked(h)
    assert q["accepted"] == []
    assert any(r.get("offered_to") == LIVE and r.get("id") == "#636" for r in q["unaccepted"])


def test_assign_refuses_absent_nick(tmp_path, monkeypatch):
    h = _home(tmp_path, monkeypatch)
    # Another seat is live on the shop; LIVE is not -> refuse.
    doc = bobreport.load_digest(h)
    doc["machines"][MID]["worker_list"] = [
        {"nick": "marchhare-29948", "state": "idle", "work": "", "updated": "t"}
    ]
    bobreport.save_digest(h, doc)
    gitclaim._write_queue(
        gitclaim.queue_path(h),
        {
            "v": 1,
            "unaccepted": [
                {
                    "task": "FR",
                    "repo": REPO,
                    "id": "#636",
                    "title": "x",
                    "url": f"https://github.com/{REPO}/issues/636",
                    "state": "open",
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    status, why = gitclaim.assign_row(h, LIVE, REPO, "FR", "#636", issue_open=lambda *_: True)
    assert status == "refused"
    assert "not in the shop channel" in str(why).lower() or "not a live seat" in str(why).lower()
    q = gitclaim._load_queue_unlocked(h)
    assert q["unaccepted"][0].get("offered_to") in ("", None)


def test_assign_refuses_to_steal_from_live_accepted(tmp_path, monkeypatch):
    h = _home(tmp_path, monkeypatch)
    other = "marchhare-29948"
    doc = bobreport.load_digest(h)
    doc["machines"][MID]["worker_list"] = [
        {"nick": LIVE, "state": "idle", "work": "", "updated": "t"},
        {"nick": other, "state": "doing", "work": "FR", "updated": "t"},
    ]
    bobreport.save_digest(h, doc)
    gitclaim._write_queue(
        gitclaim.queue_path(h),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [_accepted_row(nick=other, accepted_by=other)],
            "done": [],
        },
    )
    status, why = gitclaim.assign_row(h, LIVE, REPO, "FR", "#636", issue_open=lambda *_: True)
    assert status == "refused"
    assert "not in the unaccepted queue" in str(why) or "accepted by" in str(why).lower()
    q = gitclaim._load_queue_unlocked(h)
    assert len(q["accepted"]) == 1
    assert q["accepted"][0]["nick"] == other
