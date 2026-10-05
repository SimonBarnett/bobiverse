"""FR #2487: sibling MRB block only when another machine has an idle/free seat."""
from __future__ import annotations

import bobreport
import gitclaim
import registered_machines
import pytest


@pytest.fixture(autouse=True)
def _roster(tmp_path, monkeypatch):
    """Seat nicks only parse when machine ids are registered (see MRB #2342)."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(
        tmp_path, {"ionos", "win-mpre8vi4u6u", "marchhare"}
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    return tmp_path


def _mrb(author: str) -> dict:
    return {
        "repo": "SimonBarnett/bobiverse",
        "task": "MRB",
        "id": "#2487",
        "title": "fix: sibling idle viable",
        "url": "https://github.com/SimonBarnett/bobiverse/pull/2487",
        "author_seat": author,
        "implementer_seat": author,
    }


def test_fr2487_sibling_not_blocked_when_other_machine_seats_busy():
    row = _mrb("marchhare-35016")
    live = {
        "marchhare-35016",
        "marchhare-40208",
        "win-mpre8vi4u6u-14452",
        "win-mpre8vi4u6u-7764",
    }
    # ionos busy => not in free
    free = {"marchhare-35016", "marchhare-40208"}
    assert gitclaim.review_blocked_for_author(row, "marchhare-35016", live, free=free) is True  # exact author
    assert gitclaim.review_blocked_for_author(row, "marchhare-40208", live, free=free) is False  # sibling OK


def test_fr2487_sibling_blocked_when_other_machine_has_free_seat():
    row = _mrb("marchhare-35016")
    live = {
        "marchhare-35016",
        "marchhare-40208",
        "win-mpre8vi4u6u-14452",
        "win-mpre8vi4u6u-7764",
    }
    free = {"marchhare-35016", "marchhare-40208", "win-mpre8vi4u6u-7764"}  # ionos free
    assert gitclaim.review_blocked_for_author(row, "marchhare-40208", live, free=free) is True


def test_fr2487_free_none_preserves_legacy_live_as_free():
    row = _mrb("marchhare-35016")
    live = {"marchhare-35016", "marchhare-40208", "win-mpre8vi4u6u-7764"}
    # free=None => treat all live as free => sibling blocked
    assert gitclaim.review_blocked_for_author(row, "marchhare-40208", live, free=None) is True


def test_fr2487_free_seat_nicks_excludes_accepted(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare", "win-mpre8vi4u6u"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#1",
                    "nick": "win-mpre8vi4u6u-7764",
                    "seq": 1,
                    "ts": "t",
                    "line": "x",
                }
            ],
            "done": [],
        },
    )
    doc = bobreport.empty_digest()
    for mid, pids in {"marchhare": ["40208"], "win-mpre8vi4u6u": ["7764", "14452"]}.items():
        doc["machines"][mid] = bobreport._empty_machine(mid)
        doc["machines"][mid]["workers"] = {
            pid: {"state": "idle", "nick": f"{mid}-{pid}"} for pid in pids
        }
    bobreport.save_digest(tmp_path, doc)
    live = gitclaim.live_seat_nicks(tmp_path)
    free = gitclaim.free_seat_nicks(tmp_path, live)
    lows = {n.lower() for n in free}
    assert "marchhare-40208" in lows
    assert "win-mpre8vi4u6u-14452" in lows
    assert "win-mpre8vi4u6u-7764" not in lows  # accepted => busy
