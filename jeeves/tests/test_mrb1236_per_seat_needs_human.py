"""Hostile MRB #1236: per-seat needs_human, require_machine=any unpin, fr_done hold."""
from __future__ import annotations

import json
import time
from pathlib import Path

import gitclaim


def test_row_needs_human_only_blocks_giveup_seats():
    row = {"needs_human": True, "giveup_seats": "ionos-1,win-mpre8vi4u6u-99"}
    assert gitclaim.row_needs_human(row, "ionos-1") is True
    assert gitclaim.row_needs_human(row, "win-mpre8vi4u6u-99") is True
    assert gitclaim.row_needs_human(row, "marchhare-41928") is False
    # bare needs_human with no giveup_seats → global
    bare = {"needs_human": True}
    assert gitclaim.row_needs_human(bare, "marchhare-41928") is True
    assert gitclaim.row_needs_human({"needs_human": False}, "x") is False


def test_require_machine_any_none_star_skips_reinfer():
    title = "FR: stamp require_machine=ce-priority-dev1 on ce-priority UAT"
    for stamp in ("any", "none", "*", "-"):
        row = {
            "require_machine": stamp,
            "title": title,
            "body": "WP0 live AllowedComputer=CE-PRIORITY-DEV1",
            "labels": ["via-intake"],
            "line": title,
        }
        assert gitclaim.row_require_machine(row) == "", stamp
    # Without unpin stamp, cues still infer
    row2 = {"title": title, "body": "WP0 live", "labels": [], "line": ""}
    assert gitclaim.row_require_machine(row2) == "ce-priority-dev1"


def test_offer_skips_other_seat_after_per_seat_needs_human(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#1055",
                    "seq": 1,
                    "ts": "t",
                    "line": "FR #1055",
                    "title": "ircJeeves Stopped",
                    "labels": ["feature-request"],
                    "needs_human": True,
                    "giveup_seats": "win-mpre8vi4u6u-1",
                    "state": "open",
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    assert gitclaim.offer_focus_top(tmp_path, "win-mpre8vi4u6u-1", "#win-mpre8vi4u6u")[0] == "empty"
    st, job = gitclaim.offer_focus_top(tmp_path, "marchhare-41928", "#marchhare")
    assert st == "ok" and job["id"] == "#1055"


def test_fr_done_hold_blocks_offer_via_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = Path(tmp_path)
    key = gitclaim._lkey("SimonBarnett/bobiverse", "#1201")
    gitclaim.ledger_path(home).write_text(
        json.dumps(
            {
                "v": 1,
                "fr_done": {key: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
            }
        ),
        encoding="utf-8",
    )
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#1201",
                    "seq": 1,
                    "ts": "t",
                    "line": "x",
                    "title": "FR: already has PR",
                    "labels": ["feature-request"],
                    "state": "open",
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    led = gitclaim.ledger_load(home)
    row = gitclaim.load_unaccepted(home)[0]
    assert gitclaim.ledger_blocks(led, row, "marchhare-1", {"marchhare-1"})
    assert gitclaim.offer_focus_top(home, "marchhare-1", "#marchhare")[0] == "empty"
