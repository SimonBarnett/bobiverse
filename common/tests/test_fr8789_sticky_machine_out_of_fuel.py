"""FR #8789: machine status=out_of_fuel clears when a seat is doing/offered/idle."""
from __future__ import annotations

import bobreport


def test_fr8789_clear_sticky_when_worker_doing():
    ent = bobreport._empty_machine("redqueen")
    ent["online"] = True
    ent["status"] = "out_of_fuel"
    ent["out_of_tokens"] = True
    ent["worker_list"] = [
        {
            "nick": "redqueen-2356",
            "state": "doing",
            "work": "FR SimonBarnett/bobiverse#8750",
            "updated": "2026-11-21T19:45:00Z",
            "progress_phase": "stream",
        }
    ]
    assert bobreport.clear_sticky_machine_out_of_fuel(ent) is True
    assert ent["status"] == "I am online"
    assert ent["out_of_tokens"] is False


def test_fr8789_keep_out_of_fuel_when_only_fuel_hold_seats():
    ent = bobreport._empty_machine("redqueen")
    ent["status"] = "out_of_fuel"
    ent["out_of_tokens"] = True
    ent["worker_list"] = [
        {
            "nick": "redqueen-1",
            "state": "out_of_fuel",
            "work": "out-of-fuel",
            "updated": "2026-11-21T19:45:00Z",
        }
    ]
    assert bobreport.clear_sticky_machine_out_of_fuel(ent) is False
    assert ent["status"] == "out_of_fuel"
    assert ent["out_of_tokens"] is True


def test_fr8789_refresh_activity_clears_sticky_status():
    ent = bobreport._empty_machine("redqueen")
    ent["online"] = True
    ent["status"] = "out_of_fuel"
    ent["out_of_tokens"] = True
    ent["worker_list"] = [
        {
            "nick": "redqueen-2356",
            "state": "doing",
            "work": "FR #8750",
            "updated": "2026-11-21T19:45:00Z",
        }
    ]
    bobreport._refresh_machine_activity_from_worker_list(ent)
    assert ent["status"] == "I am online"
    assert ent["working_on"] == "FR #8750"
    assert ent["out_of_tokens"] is False


def test_fr8789_merge_out_of_fuel_status_yields_to_doing_seat():
    mid = "redqueen"
    doc = bobreport.empty_digest()
    doc["machines"][mid] = bobreport._empty_machine(mid)
    doc["machines"][mid]["online"] = True
    doc["machines"][mid]["status"] = "I am online"
    doc["machines"][mid]["worker_list"] = [
        {
            "nick": "redqueen-2356",
            "state": "doing",
            "work": "FR SimonBarnett/bobiverse#8750",
            "updated": "2026-11-21T19:40:00Z",
        }
    ]
    # Stale/peer out_of_fuel machine paint must not stick over a doing seat.
    bobreport._apply_merge_payload(
        doc,
        mid,
        {
            "online": True,
            "id": mid,
            "status": "out_of_fuel",
            "out_of_tokens": True,
            "working_on": "out-of-fuel",
            "weekly": 0,
        },
    )
    ent = doc["machines"][mid]
    assert ent["status"] == "I am online"
    assert ent.get("out_of_tokens") is False


def test_fr8789_worker_work_doing_clears_machine_status(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    import registered_machines

    registered_machines.save_registered(tmp_path, {"redqueen"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    digest = bobreport.empty_digest()
    mid = "redqueen"
    digest["machines"][mid] = bobreport._empty_machine(mid)
    digest["machines"][mid]["online"] = True
    digest["machines"][mid]["status"] = "out_of_fuel"
    digest["machines"][mid]["out_of_tokens"] = True
    digest["machines"][mid]["worker_list"] = [
        {
            "nick": "redqueen-2356",
            "state": "out_of_fuel",
            "work": "out-of-fuel",
            "updated": "2026-11-21T19:30:00Z",
        }
    ]
    bobreport.save_digest(tmp_path, digest)
    out = bobreport._apply_worker_op(
        tmp_path,
        "worker-work",
        mid,
        {
            "op": "worker-work",
            "nick": "redqueen-2356",
            "state": "doing",
            "work": "FR SimonBarnett/bobiverse#8750",
            "progress_phase": "stream",
        },
    )
    assert out.ok is True
    ent = bobreport.load_digest(tmp_path)["machines"][mid]
    assert ent["worker_list"][0]["state"] == "doing"
    assert ent["status"] == "I am online"
    assert not ent.get("out_of_tokens")
