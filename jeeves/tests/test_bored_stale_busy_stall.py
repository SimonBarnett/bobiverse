"""Fleet stall 2026-10-05: seats saying !bored were nak-busy'd 8h on a stale digest "doing"."""
from __future__ import annotations

import time
from pathlib import Path

import bobreport
import gitclaim

NICK = "marchhare-35016"


def _setup(home: Path, monkeypatch, work: str = "bobiverse MRB #2349") -> None:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["marchhare","win-mpre8vi4u6u"]}', encoding="utf-8"
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    doc = bobreport.empty_digest()
    doc["machines"]["marchhare"] = {
        "id": "marchhare",
        "online": True,
        "working_on": work,
        "worker_list": [
            {
                "nick": NICK,
                "state": "doing",
                "work": work,
                "updated": "2026-10-04T22:20:53Z",
            }
        ],
        "workers": {
            "35016": {
                "pid": "35016",
                "nick": NICK,
                "state": "doing",
                "working_on": work,
            }
        },
    }
    bobreport.save_digest(home, doc)


def _queue(home: Path, accepted: list[dict]) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": accepted},
    )


def _gate(home: Path, now: float) -> str:
    gitclaim.note_worker_activity(home, NICK, now - 10_000)
    return gitclaim.bored_gate(home, NICK, "#marchhare", now)


def test_bored_from_doing_seat_with_no_accepted_row_is_served(tmp_path, monkeypatch):
    """Reproduces the stall: MRB #2349 merged, ACC row purged, digest still 'doing' -> was nak busy forever."""
    _setup(tmp_path, monkeypatch)
    _queue(tmp_path, [])
    assert _gate(tmp_path, time.time()) == "ok"
    assert gitclaim.worker_working_on(tmp_path, NICK) == ""


def test_bored_from_seat_with_hours_old_accepted_row_is_served_and_row_dropped(
    tmp_path, monkeypatch
):
    _setup(tmp_path, monkeypatch, work="bobiverse FR #2340")
    now = time.time()
    old = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 8 * 3600))
    _queue(
        tmp_path,
        [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#2340",
                "nick": NICK,
                "accepted_ts": old,
                "ts": old,
            }
        ],
    )
    assert _gate(tmp_path, now) == "ok"
    assert gitclaim.load_queue(tmp_path)["accepted"] == []


def test_recent_accepted_row_still_busy(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, work="bobiverse FR #7")
    now = time.time()
    fresh = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 300))
    _queue(
        tmp_path,
        [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#7",
                "nick": NICK,
                "accepted_ts": fresh,
                "ts": fresh,
            }
        ],
    )
    assert _gate(tmp_path, now) == "busy"
    assert len(gitclaim.load_queue(tmp_path)["accepted"]) == 1


def test_stale_accepted_by_only_row_is_dropped(tmp_path, monkeypatch):
    """MRB #2371 hostile: ACC stamped accepted_by without nick must still heal."""
    _setup(tmp_path, monkeypatch, work="bobiverse FR #2340")
    now = time.time()
    old = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 8 * 3600))
    _queue(
        tmp_path,
        [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#2340",
                "accepted_by": NICK,
                "accepted_ts": old,
                "ts": old,
            }
        ],
    )
    assert _gate(tmp_path, now) == "ok"
    assert gitclaim.load_queue(tmp_path)["accepted"] == []
    assert gitclaim.worker_working_on(tmp_path, NICK) == ""


def test_stall_test_file_has_no_bom():
    path = Path(__file__)
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf")


def test_mrb2373_stale_busy_preserves_other_seat_acc(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, work="bobiverse FR #2340")
    now = time.time()
    old = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 8 * 3600))
    other = "win-mpre8vi4u6u-1"
    _queue(
        tmp_path,
        [
            {"repo": "SimonBarnett/bobiverse", "task": "FR", "id": "#2340", "nick": NICK,
             "accepted_ts": old, "ts": old},
            {"repo": "SimonBarnett/bobiverse", "task": "FR", "id": "#8", "nick": other,
             "accepted_ts": old, "ts": old},
        ],
    )
    assert _gate(tmp_path, now) == "ok"
    acc = gitclaim.load_queue(tmp_path)["accepted"]
    assert len(acc) == 1
    assert acc[0]["nick"] == other
    done = gitclaim.load_queue(tmp_path).get("done") or []
    assert any(str(r.get("result") or "") == "STALE_BUSY" and str(r.get("id")) == "#2340" for r in done)


def test_mrb2373_missing_accepted_ts_treated_as_stale(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, work="bobiverse FR #2340")
    now = time.time()
    _queue(
        tmp_path,
        [{"repo": "SimonBarnett/bobiverse", "task": "FR", "id": "#2340", "nick": NICK}],
    )
    assert _gate(tmp_path, now) == "ok"
    assert gitclaim.load_queue(tmp_path)["accepted"] == []
