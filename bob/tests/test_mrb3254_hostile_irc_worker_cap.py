# -*- coding: utf-8 -*-
"""Hostile MRB #3254 / FR #3181: IRC-joined agent seat cap gates."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
BOB_SCRIPTS = ROOT / "bob" / "scripts"
for p in (COMMON_SCRIPTS, BOB_SCRIPTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import worker_irc_seats as seats  # noqa: E402
import startworker as sw  # noqa: E402
import bob_worker as bw  # noqa: E402

SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
TRAY_CS = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"
TRAY_PS1 = ROOT / "bob" / "tray" / "tools" / "BobTrayStartWorker.ps1"


def _alive(pids):
    live = {int(p) for p in pids}

    def fn(pid: int) -> bool:
        return int(pid) in live

    return fn


@pytest.fixture
def seat_root(tmp_path):
    d = tmp_path / "seats"
    d.mkdir()
    return d


def test_mrb3254_machine_filter_isolates_shops(seat_root):
    seats.write_seat_irc(nick="a", pid=1, machine="marchhare", root=seat_root)
    seats.write_seat_irc(nick="b", pid=2, machine="ionos", root=seat_root)
    assert seats.count_irc_agent_seats(
        seat_root, machine="marchhare", pid_alive_fn=_alive([1, 2])
    ) == 1
    assert seats.count_irc_agent_seats(
        seat_root, machine="ionos", pid_alive_fn=_alive([1, 2])
    ) == 1


def test_mrb3254_clear_seat_frees_cap(seat_root):
    seats.write_seat_irc(nick="a1", pid=11, machine="m", root=seat_root)
    seats.write_seat_irc(nick="a2", pid=12, machine="m", root=seat_root)
    assert seats.worker_cap_refusal_irc(
        for_mode="agent", root=seat_root, machine="m", pid_alive_fn=_alive([11, 12])
    )
    seats.clear_seat_irc(pid=12, root=seat_root)
    assert (
        seats.worker_cap_refusal_irc(
            for_mode="agent", root=seat_root, machine="m", pid_alive_fn=_alive([11, 12])
        )
        == ""
    )


def test_mrb3254_maintenance_and_monitor_never_refused(seat_root):
    seats.write_seat_irc(nick="a1", pid=1, machine="m", root=seat_root)
    seats.write_seat_irc(nick="a2", pid=2, machine="m", root=seat_root)
    alive = _alive([1, 2])
    for mode in ("plan", "maintenance", "monitor"):
        assert (
            seats.worker_cap_refusal_irc(
                for_mode=mode, root=seat_root, machine="m", pid_alive_fn=alive
            )
            == ""
        )
        assert bw.worker_cap_refusal([(1, 0, "bob-worker.exe")], 99, for_mode=mode) == ""


def test_mrb3254_three_tuple_snapshot_does_not_invent_agent():
    """Production Toolhelp shape is 3-tuples; missing mode must be unknown."""
    procs = [
        (10, 0, "bob-worker.exe"),
        (11, 0, "bob-worker.exe"),
        (12, 0, "bob-worker.exe"),
    ]
    assert bw._proc_mode(procs[0]) == "unknown"
    assert sw._entry_mode(procs[0]) == "unknown"
    assert sw.count_workers(procs, modes=("agent",)) == 0
    assert bw.other_live_workers(procs, my_pid=99, modes=("agent",)) == 0


def test_mrb3254_skill_and_tray_say_irc_joined():
    skill = SKILL.read_text(encoding="utf-8-sig")
    assert "FR #3181" in skill
    assert "IRC-joined agent seats" in skill or "IRC-joined" in skill
    assert "unknown" in skill.lower() and "never agent" in skill.lower()
    cs = TRAY_CS.read_text(encoding="utf-8-sig")
    assert "CountIrcAgentSeats" in cs
    assert "IRC-joined" in cs
    assert 'return "unknown"' in cs or 'return "unknown";' in cs
    ps1 = TRAY_PS1.read_text(encoding="utf-8-sig")
    assert "FR #3181" in ps1
    assert "*.irc.json" in ps1 or ".irc.json" in ps1


def test_mrb3254_startworker_decide_ignores_process_flood(tmp_path, monkeypatch):
    """Even with many live bob-worker roots, IRC count 0 must ACK agent."""
    import os

    now = 1_800_000_000.0
    qdir = tmp_path / "q"
    qdir.mkdir()
    alive = qdir / "tray.alive"
    alive.write_text("alive", encoding="utf-8")
    os.utime(alive, (now, now))
    gate = sw.StartGate(max_workers=2, cooldown_s=0)
    monkeypatch.setattr(sw, "count_irc_agent_seats", lambda **kw: 0)
    flood = [(i, 0, "bob-worker.exe") for i in range(1, 8)]
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
        procs=lambda: flood,
        write=False,
        now=now,
    )
    assert d is not None and d.ok and d.reason == "ok"
