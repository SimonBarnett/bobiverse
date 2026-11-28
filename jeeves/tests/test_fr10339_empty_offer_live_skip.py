"""FR #10339: empty offer logs live skip; clamp without hiding mismatch."""
from __future__ import annotations

import time

import bobreport
import gitclaim
import registered_machines


def test_clamp_without_live_skip_keeps_mismatch_not_blocked_other():
    stats = {"unaccepted": 10, "offerable": 5, "out_of_focus": 0}
    clamped = gitclaim.clamp_empty_reply_stats(stats)
    assert clamped["offerable"] == 0
    assert clamped.get("blocked_other", 0) == 0
    assert clamped["offerable_live_mismatch"] == 5
    line = gitclaim.format_empty_offer_detail("marchhare-1", clamped)
    assert "offerable_live_mismatch=5" in line


def test_clamp_with_live_skip_attributes_blocked_other():
    stats = {"unaccepted": 10, "offerable": 3}
    clamped = gitclaim.clamp_empty_reply_stats(
        stats, live_skip="FR SimonBarnett/bobiverse#9:model"
    )
    assert clamped["offerable"] == 0
    assert clamped["blocked_other"] == 3
    assert clamped["live_skip"] == "FR SimonBarnett/bobiverse#9:model"
    line = gitclaim.format_empty_offer_detail("marchhare-1", clamped)
    assert "live_skip=FR SimonBarnett/bobiverse#9:model" in line


def test_bored_gate_busy_reason_pending_offer(tmp_path, monkeypatch):
    home = tmp_path
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    registered_machines.save_registered(home, {"marchhare"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    now = time.time()
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#10285",
                    "offered_to": "marchhare-1",
                    "offered_ts": gitclaim._utc_now(),
                    "title": "x",
                    "body": "y",
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    reason = gitclaim.bored_gate_busy_reason(home, "marchhare-1", now)
    assert reason.startswith("pending-offer SimonBarnett/bobiverse/FR#10285")


def test_offer_empty_notes_first_live_skip(tmp_path, monkeypatch):
    home = tmp_path
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    registered_machines.save_registered(home, {"marchhare", "walrus"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    doc = bobreport.empty_digest()
    for mid in ("marchhare", "walrus"):
        doc["machines"][mid] = bobreport._empty_machine(mid)
        doc["machines"][mid]["worker_list"] = [
            {"nick": f"{mid}-1", "state": "idle", "work": "", "updated": "t"}
        ]
    bobreport.save_digest(home, doc)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#10339",
                    "title": "chair-host: walrus only",
                    "body": "",
                    "labels": ["needs-walrus"],
                    "require_machine": "walrus",
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    st, job = gitclaim.offer_focus_top(home, "marchhare-1", "#marchhare")
    assert st == "empty"
    assert job is None
    skip = gitclaim.take_last_offer_empty_skip(home, "marchhare-1")
    assert ":require_machine" in skip