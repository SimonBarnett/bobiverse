"""FR #8429: online shop with zero workers while ungated work is waiting."""

from __future__ import annotations

import stuck_job_sweep as sweep


def test_fr8429_online_zero_workers_is_a_finding():
    machines = {
        "flamingo": {"online": True, "worker_list": [{"nick": "flamingo-1"}, {"nick": "flamingo-2"}]},
        "marchhare": {"online": True, "workers": {}},
        "offlinebox": {"online": False, "workers": []},
    }
    rows = [
        {"task": "FIX", "id": "#1"},
        {"task": "FR", "id": "#2", "needs_human": True},
    ]
    assert sweep.ungated_unaccepted_count(rows) == 1
    found = sweep.classify_empty_online_machines(machines, 1)
    assert [item["machine"] for item in found] == ["marchhare"]
    assert found[0]["stuck_reason"] == "online_zero_workers"


def test_fr8429_no_finding_without_ungated_work():
    machines = {"marchhare": {"online": True, "worker_list": []}}
    assert sweep.classify_empty_online_machines(machines, 0) == []


def test_fr8429_sweep_reports_online_zero_workers(tmp_path, monkeypatch):
    """The classifier must be on the sweep report, not only callable by hand."""
    import bobreport
    import gitclaim
    import registered_machines

    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["online"] = True
    digest["machines"]["marchhare"]["worker_list"] = []
    digest["machines"]["marchhare"]["workers"] = {}
    bobreport.save_digest(tmp_path, digest)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#8429",
                    "seq": 1,
                    "ts": "2026-11-20T10:00:00Z",
                    "line": "FR",
                    "url": "https://github.com/SimonBarnett/bobiverse/issues/8429",
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    report = sweep.run_stuck_sweep(
        tmp_path,
        now=1_900_000_000.0,
        live={"flamingo-1"},
        idle=set(),
        activity={},
        last_bored={},
        open_items=[],
        act=False,
    )
    reasons = [c.get("stuck_reason") for c in report["classified"]]
    assert "online_zero_workers" in reasons
