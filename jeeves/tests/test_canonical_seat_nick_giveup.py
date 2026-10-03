"""Short w-io-* / w-mh-* nicks must match full machine-pid giveup_seats / ledger."""
from __future__ import annotations

import time

import gitclaim


def test_canonical_worker_nick_always_machine_pid():
    assert gitclaim.canonical_worker_nick("w-io-15656") == "win-mpre8vi4u6u-15656"
    assert gitclaim.canonical_worker_nick("win-mpre8vi4u6u-15656") == "win-mpre8vi4u6u-15656"
    assert gitclaim.canonical_worker_nick("w-mh-35600") == "marchhare-35600"
    assert gitclaim.canonical_worker_nick("marchhare-35600") == "marchhare-35600"
    # both forms equal
    assert gitclaim.canonical_worker_nick("w-io-1") == gitclaim.canonical_worker_nick(
        "win-mpre8vi4u6u-1"
    )


def test_nick_in_giveup_seats_matches_short_and_full():
    row = {"giveup_seats": "win-mpre8vi4u6u-15656,marchhare-35600"}
    assert gitclaim.nick_in_giveup_seats(row, "w-io-15656") is True
    assert gitclaim.nick_in_giveup_seats(row, "win-mpre8vi4u6u-15656") is True
    assert gitclaim.nick_in_giveup_seats(row, "w-mh-35600") is True
    assert gitclaim.nick_in_giveup_seats(row, "marchhare-41928") is False


def test_row_needs_human_blocks_short_nick_when_full_in_giveup_seats():
    row = {
        "needs_human": True,
        "giveup_seats": "win-mpre8vi4u6u-15656,win-mpre8vi4u6u-20596",
    }
    assert gitclaim.row_needs_human(row, "w-io-15656") is True
    assert gitclaim.row_needs_human(row, "win-mpre8vi4u6u-15656") is True
    assert gitclaim.row_needs_human(row, "w-mh-35600") is False
    assert gitclaim.row_needs_human(row, "marchhare-35600") is False


def test_row_on_cooldown_blocks_short_nick_when_full_in_giveup_seats():
    until = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3600))
    row = {
        "cooldown_until": until,
        "giveup_seats": "win-mpre8vi4u6u-15656",
    }
    now = time.time()
    assert gitclaim.row_on_cooldown(row, now, "w-io-15656") is True
    assert gitclaim.row_on_cooldown(row, now, "win-mpre8vi4u6u-15656") is True
    assert gitclaim.row_on_cooldown(row, now, "w-mh-1") is False


def test_row_gave_up_by_short_matches_full():
    row = {"giveup_seats": "win-mpre8vi4u6u-20596"}
    assert gitclaim.row_gave_up_by(row, "w-io-20596") is True
    assert gitclaim.row_gave_up_by(row, "win-mpre8vi4u6u-20596") is True
    assert gitclaim.row_gave_up_by(row, "w-io-15656") is False


def test_purge_dead_mrb_accepted_moves_merged_to_done(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "MRB",
                    "id": "#1236",
                    "seq": 1,
                    "ts": "t",
                    "line": "MRB #1236",
                    "url": "https://github.com/SimonBarnett/bobiverse/pull/1236",
                    "nick": "win-mpre8vi4u6u-1",
                    "merged": True,
                }
            ],
            "done": [],
        },
    )
    with gitclaim._lock(tmp_path):
        doc = gitclaim._load_queue_unlocked(tmp_path)
        # queue serialize drops ``merged``; live open-check is required (same as chair).
        n = gitclaim._purge_dead_mrb_accepted(doc, pr_exists=lambda repo, num: False)
        assert n == 1
        assert doc["accepted"] == []
        assert doc["done"][0]["id"] == "#1236"
        assert doc["done"][0]["result"] == "MERGED"
        gitclaim._write_queue(gitclaim.queue_path(tmp_path), doc)


def test_offer_blocks_short_nick_after_full_form_giveup(tmp_path, monkeypatch):
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
                    "giveup_seats": "win-mpre8vi4u6u-15656",
                    "state": "open",
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    assert gitclaim.offer_focus_top(tmp_path, "w-io-15656", "#win-mpre8vi4u6u")[0] == "empty"
    assert gitclaim.offer_focus_top(tmp_path, "win-mpre8vi4u6u-15656", "#win-mpre8vi4u6u")[0] == "empty"
    st, job = gitclaim.offer_focus_top(tmp_path, "w-mh-41928", "#marchhare")
    assert st == "ok" and job["id"] == "#1055"
    # offered_to stamped as canonical machine-pid
    assert job["offered_to"] == "marchhare-41928"
