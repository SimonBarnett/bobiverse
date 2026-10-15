# -*- coding: utf-8 -*-
"""FR #4307: worker cap must not undercount live agent seats when run\\seats markers are missing."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import worker_irc_seats as seats  # noqa: E402
import startworker as sw  # noqa: E402


def _alive_set(pids):
    live = {int(p) for p in pids}

    def fn(pid: int) -> bool:
        return int(pid) in live

    return fn


@pytest.fixture
def seat_root(tmp_path):
    d = tmp_path / "seats"
    d.mkdir()
    return d


def test_two_live_agent_procs_no_seat_files_refuse_third(seat_root):
    """Acceptance: two live workers, empty seats dir -> cap reports 2 and refuses."""
    procs = [
        (101, 1, "bob-worker.exe", "--mode agent"),
        (102, 1, "bob-worker.exe", "--mode agent"),
    ]
    msg = seats.worker_cap_refusal_irc(
        for_mode="agent",
        root=seat_root,
        machine="marchhare",
        pid_alive_fn=_alive_set([101, 102]),
        procs=procs,
    )
    assert msg.startswith("max 2 workers")
    assert seats.count_cap_agent_seats(
        seat_root,
        machine="marchhare",
        pid_alive_fn=_alive_set([101, 102]),
        procs=procs,
    ) == 2


def test_one_marker_plus_one_live_without_marker_counts_two(seat_root):
    """Acceptance: one seat file + one live process without file -> 2."""
    seats.write_seat_irc(nick="marchhare-8824", pid=101, machine="marchhare", root=seat_root)
    procs = [
        (101, 1, "bob-worker-9705af74d30d.exe", "--mode agent"),
        (202, 1, "bob-worker-3dc46f458b02.exe", "--mode agent"),
    ]
    n = seats.count_cap_agent_seats(
        seat_root,
        machine="marchhare",
        pid_alive_fn=_alive_set([101, 202]),
        procs=procs,
    )
    assert n == 2
    assert seats.worker_cap_refusal_irc(
        for_mode="agent",
        root=seat_root,
        machine="marchhare",
        pid_alive_fn=_alive_set([101, 202]),
        procs=procs,
    ).startswith("max 2 workers")


def test_stale_seat_file_without_live_process_not_counted(seat_root):
    """Acceptance: stale marker with dead pid is not counted."""
    seats.write_seat_irc(nick="ghost", pid=999, machine="marchhare", root=seat_root)
    procs = [(101, 1, "bob-worker.exe", "--mode agent")]
    n = seats.count_cap_agent_seats(
        seat_root,
        machine="marchhare",
        pid_alive_fn=_alive_set([101]),
        procs=procs,
    )
    assert n == 1
    assert not (seat_root / "ghost.irc.json").exists()
    assert (
        seats.worker_cap_refusal_irc(
            for_mode="agent",
            root=seat_root,
            machine="marchhare",
            pid_alive_fn=_alive_set([101]),
            procs=procs,
        )
        == ""
    )


def test_plan_mode_still_uncapped_with_two_live_agents(seat_root):
    procs = [
        (101, 1, "bob-worker.exe", "--mode agent"),
        (102, 1, "bob-worker.exe", "--mode agent"),
    ]
    assert (
        seats.worker_cap_refusal_irc(
            for_mode="plan",
            root=seat_root,
            machine="m",
            pid_alive_fn=_alive_set([101, 102]),
            procs=procs,
        )
        == ""
    )


def test_startworker_decide_uses_proc_reconcile(tmp_path, monkeypatch):
    qdir = tmp_path / "q"
    qdir.mkdir()
    (qdir / "tray.alive").write_text("1", encoding="utf-8")
    (qdir / "engine.alive").write_text("1", encoding="utf-8")
    gate = sw.StartGate(max_workers=2, cooldown_s=0)
    # Empty seats dir but two live agent procs -> NACK cap
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    (tmp_path / "la" / "Bobiverse" / "worker" / "run" / "seats").mkdir(parents=True)
    d = sw.decide(
        body="!startworker agent",
        nick="simon",
        account="simon",
        channel="#marchhare",
        local_machine="marchhare",
        gate=gate,
        qdir=qdir,
        machine_of_nick=lambda n: None,
        owners={"simon"},
        procs=lambda: [
            (10, 0, "bob-worker.exe", "--mode agent"),
            (11, 0, "bob-worker.exe", "--mode agent"),
        ],
        write=False,
    )
    assert d is not None and (not d.ok) and d.reason == "cap"
