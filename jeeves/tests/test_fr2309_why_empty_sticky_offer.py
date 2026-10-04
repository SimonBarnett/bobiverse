"""FR #2309: why-empty bored stats (self-MRB/ledger/sticky) + sticky no-ACK rebroadcast cap."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("JEEVES_OWNER_ACCOUNT", "simon")
    for k in ("JEEVES_FOCUS_MUTATORS", "JEEVES_FOCUS_MUTATOR_ACCOUNTS"):
        monkeypatch.delenv(k, raising=False)
    registered_machines.save_registered(
        tmp_path, {"ionos", "ce-priority-dev1", "win-mpre8vi4u6u", "marchhare", "flamingo"}
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    return tmp_path


def _row(repo, task, num, seq, **kw):
    r = {
        "repo": repo,
        "task": task,
        "id": f"#{num}",
        "seq": seq,
        "ts": f"2026-10-01T10:00:{seq:02d}Z",
        "line": "x",
    }
    r.update(kw)
    return r


def _queue(home, rows):
    gitclaim._write_queue(
        gitclaim.queue_path(home), {"v": 1, "unaccepted": rows, "accepted": []}
    )


def _ts(age_s: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=age_s)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def test_fr2309_format_nothing_queued_includes_self_mrb_ledger_sticky():
    rich = gitclaim.format_empty_offer_detail(
        "marchhare-1",
        {
            "unaccepted": 41,
            "offerable": 0,
            "out_of_focus": 36,
            "require_machine": 2,
            "self_mrb": 1,
            "ledger": 1,
            "sticky_offered": 1,
        },
    )
    assert "0 offerable under focus" in rich
    assert "self_mrb=1" in rich
    assert "ledger=1" in rich
    assert "sticky=1" in rich


def test_fr2309_summarize_empty_offer_counts_self_mrb_and_sticky(_home, monkeypatch):
    doc = bobreport.empty_digest()
    for mid, pids in (
        ("marchhare", ("40208", "35016")),
        ("win-mpre8vi4u6u", ("14452",)),
    ):
        doc["machines"][mid] = bobreport._empty_machine(mid)
        doc["machines"][mid]["workers"] = {p: {"state": "idle"} for p in pids}
    bobreport.save_digest(_home, doc)
    _queue(
        _home,
        [
            _row(
                "SimonBarnett/bobiverse",
                "MRB",
                2292,
                1,
                url="https://github.com/SimonBarnett/bobiverse/pull/2292",
                implementer_seat="marchhare-40208",
                offered_to="win-mpre8vi4u6u-14452",
                offered_ts=_ts(30),
            ),
            _row(
                "SimonBarnett/bobiverse",
                "FR",
                1714,
                2,
                url="https://github.com/SimonBarnett/bobiverse/issues/1714",
            ),
            _row(
                "SimonBarnett/Club-Madeira",
                "FR",
                9,
                3,
                url="https://github.com/SimonBarnett/Club-Madeira/issues/9",
            ),
        ],
    )
    fi.handle_focus_cmd(_home, "SimonBarnett/bobiverse")
    fi.handle_focus_cmd(_home, "strict on")
    stats = gitclaim.summarize_empty_offer(_home, "marchhare-40208")
    assert stats["unaccepted"] == 3
    assert stats["out_of_focus"] >= 1
    assert stats.get("self_mrb", 0) >= 1
    assert stats.get("sticky_offered", 0) >= 1


def test_fr2309_sticky_rebroadcast_does_not_refresh_offered_ts(_home, monkeypatch):
    doc = bobreport.empty_digest()
    doc["machines"]["win-mpre8vi4u6u"] = bobreport._empty_machine("win-mpre8vi4u6u")
    doc["machines"]["win-mpre8vi4u6u"]["workers"] = {"14452": {"state": "idle"}}
    doc["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    doc["machines"]["marchhare"]["workers"] = {"40208": {"state": "idle"}}
    bobreport.save_digest(_home, doc)
    first_ts = _ts(40)
    _queue(
        _home,
        [
            _row(
                "SimonBarnett/bobiverse",
                "MRB",
                2292,
                1,
                url="https://github.com/SimonBarnett/bobiverse/pull/2292",
                implementer_seat="marchhare-40208",
                offered_to="win-mpre8vi4u6u-14452",
                offered_ts=first_ts,
                offered_count=1,
            )
        ],
    )
    st, job = gitclaim.offer_focus_top(
        _home, "win-mpre8vi4u6u-14452", "#win-mpre8vi4u6u", now=time.time()
    )
    assert st == "ok" and job is not None
    assert job["offered_to"] == "win-mpre8vi4u6u-14452"
    assert job.get("offered_ts") == first_ts
    assert int(job.get("offered_count") or 0) == 2


def test_fr2309_sticky_max_clears_offer_for_other_seat(_home):
    doc = bobreport.empty_digest()
    for mid, pids in (
        ("marchhare", ("40208",)),
        ("win-mpre8vi4u6u", ("14452",)),
        ("flamingo", ("99",)),
    ):
        doc["machines"][mid] = bobreport._empty_machine(mid)
        doc["machines"][mid]["workers"] = {p: {"state": "idle"} for p in pids}
    bobreport.save_digest(_home, doc)
    _queue(
        _home,
        [
            _row(
                "SimonBarnett/bobiverse",
                "MRB",
                2292,
                1,
                url="https://github.com/SimonBarnett/bobiverse/pull/2292",
                implementer_seat="marchhare-40208",
                offered_to="win-mpre8vi4u6u-14452",
                offered_ts=_ts(20),
                offered_count=gitclaim.OFFER_STICKY_MAX,
            )
        ],
    )
    # Sticky seat at max: cleared + skipped
    st1, _job1 = gitclaim.offer_focus_top(
        _home, "win-mpre8vi4u6u-14452", "#win-mpre8vi4u6u", now=time.time()
    )
    assert st1 == "empty"
    rows = gitclaim.load_unaccepted(_home)
    assert "win-mpre8vi4u6u-14452" in [
        (gitclaim.canonical_worker_nick(x) or x)
        for x in (rows[0].get("sticky_skip_seats") or [])
    ]
    # Other machine seat can take it
    st2, job2 = gitclaim.offer_focus_top(_home, "flamingo-99", "#flamingo", now=time.time())
    assert st2 == "ok"
    assert job2["offered_to"] == "flamingo-99"
