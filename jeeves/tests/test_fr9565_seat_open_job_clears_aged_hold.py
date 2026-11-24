"""FR #9565: seat_open_job must not report held after aged offer purge (FR #9403).

build-jeeves on main failed test_fr4089_one_open_job_per_seat::test_old_offer_*
because the pin still expected ``held`` after OFFER_TIMEOUT while product
``purge_stale_offered_pins`` (FR #9403) clears seat-holds with the pin.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import bobreport
import focus_ignore as fi
import gitclaim
import pytest
import registered_machines

REPO = "SimonBarnett/bobiverse"
ME = "marchhare-35600"
SHOP = "#marchhare"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    registered_machines.save_registered(tmp_path, {"marchhare", "flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["worker_list"] = [
        {"nick": ME, "state": "idle", "work": "", "updated": "2026-10-14T20:00:00Z"},
    ]
    bobreport.save_digest(tmp_path, digest)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    fi.handle_focus_cmd(tmp_path, REPO)
    return tmp_path


def _ts(ago_s: float) -> str:
    t = datetime.now(timezone.utc) - timedelta(seconds=ago_s)
    return t.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def test_fr9565_fresh_offer_busy_aged_offer_free(home: Path):
    row = {
        "repo": REPO,
        "task": "FR",
        "id": "#10",
        "seq": 10,
        "ts": "2026-10-11T10:00:00Z",
        "line": f"FR {REPO}#10",
        "url": f"https://github.com/{REPO}/issues/10",
        "title": "FR 10",
        "state": "open",
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": [], "workers": {}},
    )
    n, job = gitclaim.offer_after_done(home, ME, SHOP, say=lambda *_a, **_k: True)
    assert n == 1 and job["id"] == "#10"
    assert gitclaim.seat_open_job(home, ME).startswith(("offered", "held"))

    with gitclaim._lock(home):
        doc = gitclaim._load_queue_unlocked(home)
        for r in doc["unaccepted"]:
            if r.get("offered_to"):
                r["offered_ts"] = _ts(600)
        gitclaim._write_queue(gitclaim.queue_path(home), doc)
        holds = gitclaim._load_seat_holds_unlocked(home)
        holds[ME]["ts"] = _ts(600)
        gitclaim._save_seat_holds_unlocked(home, holds)

    assert gitclaim.seat_pending_offer(home, ME) is None
    assert gitclaim.seat_open_job(home, ME) == ""
    assert gitclaim._seat_key(ME) not in gitclaim._load_seat_holds_unlocked(home)
