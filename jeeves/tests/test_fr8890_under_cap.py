"""FR #8890: under-cap is a finding when an online shop is below cap and work is offerable."""
from __future__ import annotations

import sys
from pathlib import Path

MON = Path(__file__).resolve().parents[1] / "tools" / "monitor"
sys.path.insert(0, str(MON))

import idle_seats  # noqa: E402


def test_under_cap_one_of_two_with_offerable():
    dig = {
        "queue": {"offerable_count": 50},
        "machines": {
            "marchhare": {
                "online": True,
                "workers": [{"nick": "marchhare-25376", "state": "doing"}],
            }
        },
    }
    rows = idle_seats.collect_under_cap(dig, 50)
    assert rows == [{"machine": "marchhare", "live": 1, "cap": 2}]


def test_under_cap_silent_when_full_or_no_work():
    full = {"machines": {"marchhare": {"online": True, "workers": [{}, {}]}}}
    assert idle_seats.collect_under_cap(full, 10) == []
    short = {"machines": {"marchhare": {"online": True, "workers": [{}]}}}
    assert idle_seats.collect_under_cap(short, 0) == []
    assert idle_seats.collect_under_cap({"machines": {"m": {"online": False, "workers": []}}}, 4) == []
