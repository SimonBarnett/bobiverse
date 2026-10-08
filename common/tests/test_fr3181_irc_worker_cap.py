# -*- coding: utf-8 -*-
"""FR #3181: 2-worker cap counts only IRC-joined agent seats."""
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


def test_write_and_count_live_seats(seat_root):
    seats.write_seat_irc(nick="marchhare-1", pid=101, machine="marchhare", root=seat_root)
    seats.write_seat_irc(nick="marchhare-2", pid=102, machine="marchhare", root=seat_root)
    seats.write_seat_irc(nick="dead-seat", pid=999, machine="marchhare", root=seat_root)
    n = seats.count_irc_agent_seats(
        seat_root, machine="marchhare", pid_alive_fn=_alive_set([101, 102])
    )
    assert n == 2
    assert not (seat_root / "dead-seat.irc.json").exists()


def test_plan_mode_never_refused(seat_root):
    seats.write_seat_irc(nick="a1", pid=1, machine="m", root=seat_root)
    seats.write_seat_irc(nick="a2", pid=2, machine="m", root=seat_root)
    assert (
        seats.worker_cap_refusal_irc(
            for_mode="plan",
            root=seat_root,
            machine="m",
            pid_alive_fn=_alive_set([1, 2]),
        )
        == ""
    )


def test_two_irc_agents_refuse_third(seat_root):
    seats.write_seat_irc(nick="a1", pid=1, machine="m", root=seat_root)
    seats.write_seat_irc(nick="a2", pid=2, machine="m", root=seat_root)
    msg = seats.worker_cap_refusal_irc(
        for_mode="agent",
        root=seat_root,
        machine="m",
        pid_alive_fn=_alive_set([1, 2]),
    )
    assert msg.startswith("max 2 workers")
    assert "IRC-joined" in msg


def test_two_agent_procs_without_irc_markers_allow_third(seat_root):
    assert (
        seats.worker_cap_refusal_irc(
            for_mode="agent",
            root=seat_root,
            machine="m",
            pid_alive_fn=_alive_set([1, 2, 3]),
        )
        == ""
    )


def test_startworker_decide_irc_cap(tmp_path, monkeypatch):
    qdir = tmp_path / "q"
    qdir.mkdir()
    (qdir / "tray.alive").write_text("1", encoding="utf-8")
    gate = sw.StartGate(max_workers=2, cooldown_s=0)

    monkeypatch.setattr(sw, "count_irc_agent_seats", lambda **kw: 0)
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
        procs=lambda: [],
        write=False,
    )
    assert d is not None and d.ok and d.reason == "ok"

    monkeypatch.setattr(sw, "count_irc_agent_seats", lambda **kw: 2)
    d2 = sw.decide(
        body="!startworker agent",
        nick="simon",
        account="simon",
        channel="#marchhare",
        local_machine="marchhare",
        gate=gate,
        qdir=qdir,
        machine_of_nick=lambda n: None,
        owners={"simon"},
        procs=lambda: [(10, 0, "bob-worker.exe"), (11, 0, "bob-worker.exe")],
        write=False,
    )
    assert d2 is not None and (not d2.ok) and d2.reason == "cap"

    d3 = sw.decide(
        body="!startworker plan",
        nick="simon",
        account="simon",
        channel="#marchhare",
        local_machine="marchhare",
        gate=gate,
        qdir=qdir,
        machine_of_nick=lambda n: None,
        owners={"simon"},
        procs=lambda: [],
        write=False,
    )
    assert d3 is not None and d3.ok


def test_bob_worker_cap_refusal_uses_irc(monkeypatch):
    bob_scripts = ROOT.parent / "bob" / "scripts"
    if str(bob_scripts) not in sys.path:
        sys.path.insert(0, str(bob_scripts))
    import bob_worker as bw

    procs = [
        (1, 0, "bob-worker.exe"),
        (2, 0, "bob-worker.exe"),
        (3, 0, "bob-worker.exe"),
    ]
    monkeypatch.setattr(bw, "count_irc_agent_seats", lambda **kw: 2)
    assert bw.worker_cap_refusal(procs, my_pid=99, for_mode="agent")
    assert bw.worker_cap_refusal(procs, my_pid=99, for_mode="plan") == ""

    monkeypatch.setattr(bw, "count_irc_agent_seats", lambda **kw: 0)
    assert bw.worker_cap_refusal(procs, my_pid=99, for_mode="agent") == ""


def test_proc_mode_unknown_when_no_cmdline():
    bob_scripts = ROOT.parent / "bob" / "scripts"
    if str(bob_scripts) not in sys.path:
        sys.path.insert(0, str(bob_scripts))
    import bob_worker as bw

    assert bw._proc_mode((1, 0, "bob-worker.exe")) == "unknown"
    assert bw._proc_mode((1, 0, "bob-worker.exe", "--mode plan")) == "plan"


def test_startworker_entry_mode_unknown():
    assert sw._entry_mode((1, 0, "bob-worker.exe")) == "unknown"
    assert sw.count_workers([(1, 0, "bob-worker.exe"), (2, 0, "bob-worker.exe")], modes=("agent",)) == 0
