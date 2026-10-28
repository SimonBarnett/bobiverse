"""FR #5135: !cleargiveup owner/repo#N [seat] clears queue + seat-ledger atomically."""
from __future__ import annotations

import gitclaim


def test_parse_cleargiveup_cmd():
    assert gitclaim.parse_cleargiveup_cmd("!cleargiveup SimonBarnett/bobiverse#5134") == (
        "SimonBarnett/bobiverse",
        "#5134",
        "",
    )
    assert gitclaim.parse_cleargiveup_cmd("!cleargiveup o/a#1 flamingo-9") == (
        "o/a",
        "#1",
        "flamingo-9",
    )
    assert gitclaim.parse_cleargiveup_cmd("!cleargiveup") is None
    assert gitclaim.parse_cleargiveup_cmd("!assign x o/a FR 1") is None


def test_clear_giveup_job_all_stamps(tmp_path):
    home = tmp_path
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "accepted": [],
            "unaccepted": [
                {
                    "repo": "o/a",
                    "task": "FR",
                    "id": "#1",
                    "needs_human": True,
                    "giveup_count": 3,
                    "giveup_seats": "flamingo-1,marchhare-2",
                    "cooldown_until": "2099-01-01T00:00:00Z",
                    "giveup_ts": "2026-10-01T00:00:00Z",
                }
            ],
        },
    )
    gitclaim.ledger_giveup(home, "flamingo-1", "o/a", "FR", "#1")
    gitclaim.ledger_giveup(home, "marchhare-2", "o/a", "MRB", "#1")
    out = gitclaim.clear_giveup_job(home, "o/a", "#1")
    assert out["ok"] is True
    assert out["queue_rows"] == 1
    assert out["ledger"] >= 1
    row = gitclaim.load_unaccepted(home)[0]
    assert not row.get("needs_human")
    assert not row.get("giveup_seats")
    assert not row.get("cooldown_until")
    assert not row.get("giveup_ts")
    assert int(row.get("giveup_count") or 0) == 0
    led = gitclaim.ledger_load(home)
    assert "o/a#1" not in (led.get("giveup") or {})


def test_clear_giveup_job_one_seat(tmp_path):
    home = tmp_path
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "accepted": [],
            "unaccepted": [
                {
                    "repo": "o/a",
                    "task": "FR",
                    "id": "#1",
                    "needs_human": True,
                    "giveup_count": 2,
                    "giveup_seats": "flamingo-1,marchhare-2",
                    "cooldown_until": "2099-01-01T00:00:00Z",
                    "giveup_ts": "2026-10-01T00:00:00Z",
                }
            ],
        },
    )
    gitclaim.ledger_giveup(home, "flamingo-1", "o/a", "FR", "#1")
    gitclaim.ledger_giveup(home, "marchhare-2", "o/a", "FR", "#1")
    out = gitclaim.clear_giveup_job(home, "o/a", "#1", seat="flamingo-1")
    assert out["ok"] is True
    row = gitclaim.load_unaccepted(home)[0]
    assert row.get("needs_human") is True
    assert "flamingo-1" not in str(row.get("giveup_seats") or "")
    assert "marchhare-2" in str(row.get("giveup_seats") or "")
    led = gitclaim.ledger_load(home)
    bucket = (led.get("giveup") or {}).get("o/a#1") or {}
    assert "flamingo-1" not in bucket
    assert "marchhare-2" in bucket
