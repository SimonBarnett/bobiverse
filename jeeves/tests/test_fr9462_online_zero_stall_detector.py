"""FR #9462: stall detector fingerprint stall:online-zero-workers:<machine>."""
from __future__ import annotations

import stall_detectors as sd


def test_detect_online_zero_workers_fingerprint():
    snap = {
        "offerable_count": 17,
        "machines": {
            "flamingo": {"online": True, "workers": {"1": {"nick": "flamingo-1"}}},
            "marchhare": {"online": True, "workers": {}},
            "redqueen": {"online": True, "worker_list": []},
            "offline": {"online": False, "workers": []},
        },
    }
    found = sd.detect_online_zero_workers(snap)
    assert {f["key"] for f in found} == {"marchhare", "redqueen"}
    all_f = sd.detect_all(snap)
    fps = {f["fingerprint"] for f in all_f if f.get("id") == sd.ONLINE_ZERO_WORKERS_ID}
    assert fps == {
        "stall:online-zero-workers:marchhare",
        "stall:online-zero-workers:redqueen",
    }
    assert all(f["title"].startswith("stall:online-zero-workers:") for f in found)


def test_detect_online_zero_silent_without_offerable():
    snap = {
        "offerable_count": 0,
        "machines": {"marchhare": {"online": True, "workers": []}},
    }
    assert sd.detect_online_zero_workers(snap) == []
