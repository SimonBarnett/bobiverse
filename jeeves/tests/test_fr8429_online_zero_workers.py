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
