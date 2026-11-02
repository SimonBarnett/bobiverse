"""FR #5920: quiet idle seats + offerable work -> digest flag + shop nudge.

#5900 expected #2: when an idle seat stops asking !bored for >2 min and
ungated offerable work exists, Jeeves must nudge or report (rule
``idle_quiet_offerable``), distinct from ``unaccepted_starved``.
"""
from __future__ import annotations

import time
from pathlib import Path

import bobreport
import focus_ignore
import gitclaim
import registered_machines
import stuck_job_sweep as sweep

REPO = "SimonBarnett/bobiverse"
NICK = "flamingo-72904"
NOW = 1_900_000_000.0


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [
        {"nick": NICK, "state": "idle"},
    ]
    bobreport.save_digest(tmp_path, digest)
    focus_ignore.handle_focus_cmd(tmp_path, f"high {REPO}")
    return tmp_path


def _offerable_fr_row(*, age_s=4000):
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - float(age_s)))
    return {
        "repo": REPO,
        "task": "FR",
        "id": "#5920",
        "seq": 1,
        "url": f"https://github.com/{REPO}/issues/5920",
        "ts": ts,
        "event": "issues",
        "line": "FR",
        "title": "quiet idle nudge",
        "labels": ["feature-request", "via-intake"],
    }


def test_classify_quiet_idle_when_offerable_and_lag_over_2min(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [_offerable_fr_row()], "accepted": [], "done": []},
    )
    last_bored = {NICK: NOW - (sweep.QUIET_IDLE_OFFERABLE_S + 30)}
    found = sweep.classify_quiet_idle_offerable(
        home,
        idle={NICK},
        last_bored=last_bored,
        last_activity={},
        accepted=[],
        now=NOW,
    )
    assert found, "expected idle_quiet_offerable finding"
    assert found[0]["stuck"] is True
    assert found[0]["stuck_reason"] == "idle_quiet_offerable"
    assert found[0]["holder"] == NICK
    assert found[0]["age_s"] >= sweep.QUIET_IDLE_OFFERABLE_S
    assert int(found[0].get("offerable") or 0) >= 1
    # Distinct from job starve rule.
    assert found[0]["stuck_reason"] != "unaccepted_starved"


def test_no_finding_when_fresh_bored_or_no_offerable(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [_offerable_fr_row()], "accepted": [], "done": []},
    )
    fresh = sweep.classify_quiet_idle_offerable(
        home,
        idle={NICK},
        last_bored={NICK: NOW - 30},
        accepted=[],
        now=NOW,
    )
    assert fresh == []

    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [], "done": []},
    )
    empty = sweep.classify_quiet_idle_offerable(
        home,
        idle={NICK},
        last_bored={NICK: NOW - 500},
        accepted=[],
        now=NOW,
    )
    assert empty == []


def test_no_finding_without_first_bored_stamp(tmp_path, monkeypatch):
    """Seats with activity but no !bored stamp stay excluded (FR #5920)."""
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [_offerable_fr_row()], "accepted": [], "done": []},
    )
    found = sweep.classify_quiet_idle_offerable(
        home,
        idle={NICK},
        last_bored={},
        last_activity={NICK: NOW - 500},
        accepted=[],
        now=NOW,
    )
    assert found == []


def test_recent_activity_skips_quiet_idle(tmp_path, monkeypatch):
    """FR #5203 parity: recent shop activity resets the quiet clock."""
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [_offerable_fr_row()], "accepted": [], "done": []},
    )
    found = sweep.classify_quiet_idle_offerable(
        home,
        idle={NICK},
        last_bored={NICK: NOW - 500},
        last_activity={NICK: NOW - 10},
        accepted=[],
        now=NOW,
    )
    assert found == []


def test_run_stuck_sweep_flags_and_shop_nudges(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [_offerable_fr_row()], "accepted": [], "done": []},
    )
    gitclaim.record_last_bored(home, NICK, now=NOW - 200)
    # Hostile: omit last_bored so run_stuck_sweep loads merge_last_bored (MRB #5921).
    report = sweep.run_stuck_sweep(
        home,
        now=NOW,
        live={NICK},
        idle={NICK},
        activity={},
        act=True,
        open_items=[],
    )
    quiet = [
        s
        for s in (report.get("stuck") or [])
        if s.get("stuck_reason") == "idle_quiet_offerable"
    ]
    assert quiet, report.get("stuck")
    assert int(report.get("actions", {}).get("nudged") or 0) >= 1
    outbox = Path(bobreport.fleet_digest_home(home)) / "chair-outbox.txt"
    text = outbox.read_text(encoding="utf-8") if outbox.is_file() else ""
    assert "nudge:" in text and NICK in text
    assert "PRIVMSG #flamingo :" in text or "#flamingo" in text
    # Cooldown: second sweep must not re-nudge immediately.
    report2 = sweep.run_stuck_sweep(
        home,
        now=NOW + 30,
        live={NICK},
        idle={NICK},
        activity={},
        act=True,
        open_items=[],
    )
    assert int(report2.get("actions", {}).get("nudged") or 0) == 0
