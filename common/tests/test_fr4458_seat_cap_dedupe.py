# -*- coding: utf-8 -*-
"""FR #4458: one onefile seat must count once when the IRC marker pid is the child and the cap root is the bootloader."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import worker_irc_seats as seats  # noqa: E402


def _alive_set(pids):
    live = {int(p) for p in pids}

    def fn(pid: int) -> bool:
        return int(pid) in live

    return fn


def test_onefile_child_marker_and_bootloader_root_count_as_one(tmp_path):
    seat_root = tmp_path / "seats"
    seat_root.mkdir()
    # IRC marker is the onefile child; process scan root is the bootloader.
    seats.write_seat_irc(nick="marchhare-50", pid=50, machine="marchhare", root=seat_root)
    procs = [
        (100, 1, "bob-worker-aaa.exe", "--mode agent"),
        (50, 100, "bob-worker-aaa.exe", "--mode agent"),
    ]
    n = seats.count_cap_agent_seats(
        seat_root,
        machine="marchhare",
        pid_alive_fn=_alive_set([50, 100]),
        procs=procs,
    )
    assert n == 1
    assert seats.worker_cap_refusal_irc(
        for_mode="agent",
        root=seat_root,
        machine="marchhare",
        pid_alive_fn=_alive_set([50, 100]),
        procs=procs,
    ) == ""


def test_two_onefile_seats_still_hit_the_cap(tmp_path):
    seat_root = tmp_path / "seats"
    seat_root.mkdir()
    seats.write_seat_irc(nick="marchhare-50", pid=50, machine="marchhare", root=seat_root)
    seats.write_seat_irc(nick="marchhare-70", pid=70, machine="marchhare", root=seat_root)
    procs = [
        (100, 1, "bob-worker-aaa.exe", "--mode agent"),
        (50, 100, "bob-worker-aaa.exe", "--mode agent"),
        (200, 1, "bob-worker-bbb.exe", "--mode agent"),
        (70, 200, "bob-worker-bbb.exe", "--mode agent"),
    ]
    n = seats.count_cap_agent_seats(
        seat_root,
        machine="marchhare",
        pid_alive_fn=_alive_set([50, 70, 100, 200]),
        procs=procs,
    )
    assert n == 2
    assert seats.worker_cap_refusal_irc(
        for_mode="agent",
        root=seat_root,
        machine="marchhare",
        pid_alive_fn=_alive_set([50, 70, 100, 200]),
        procs=procs,
    ).startswith("max 2 workers")


def test_marker_without_process_tree_still_counts_beside_another_root(tmp_path):
    """FR #4307 disjoint case stays: unknown-cmdline marker pid + a different agent root = 2."""
    seat_root = tmp_path / "seats"
    seat_root.mkdir()
    seats.write_seat_irc(nick="marchhare-10", pid=10, machine="marchhare", root=seat_root)
    procs = [
        (10, 1, "bob-worker.exe", ""),
        (202, 1, "bob-worker-bbb.exe", "--mode agent"),
        (203, 202, "bob-worker-bbb.exe", "--mode agent"),
    ]
    n = seats.count_cap_agent_seats(
        seat_root,
        machine="marchhare",
        pid_alive_fn=_alive_set([10, 202, 203]),
        procs=procs,
    )
    assert n == 2
