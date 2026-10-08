"""FR #2522 / FR #3181: 2-seat cap is IRC-joined agent-only; plan + maintenance start on top."""
from __future__ import annotations

import bob_worker as bw
import startworker as sw
import worker_irc_seats as seats


def _agent(*pids):
    out = []
    for p in pids:
        out.append((p, 1, "bob-worker.exe", "agent"))
        out.append((p + 1, p, "bob-worker.exe", "agent"))  # onefile child
    return out


def _mixed():
    return (
        _agent(100, 200)
        + [(300, 1, "bob-worker.exe", "plan"), (301, 300, "bob-worker.exe", "plan")]
        + [(400, 1, "bob-worker.exe", "maintenance"), (401, 400, "bob-worker.exe", "maintenance")]
    )


def test_fr2522_other_live_workers_counts_agents_only():
    assert bw.other_live_workers(_mixed(), 999) == 2
    assert bw.other_live_workers(_mixed(), 999, modes=("agent", "plan")) == 3


def test_fr2522_plan_and_maintenance_never_refused_by_cap(monkeypatch, tmp_path):
    monkeypatch.setattr(bw, "snapshot_procs", lambda: _agent(200, 300))
    monkeypatch.setattr(bw, "_state_root", lambda: tmp_path)
    monkeypatch.setattr(bw, "ensure_console", lambda *a, **k: True)
    monkeypatch.setattr(bw.time, "sleep", lambda s: None)
    # FR #3181: two IRC-joined agents → refuse third agent
    monkeypatch.setattr(bw, "count_irc_agent_seats", lambda **kw: 2)
    started = []
    monkeypatch.setattr(bw, "run_agent", lambda *a, **k: started.append("agent") or 0)
    monkeypatch.setattr(bw, "run_plan", lambda *a, **k: started.append("plan") or 0)
    monkeypatch.setattr(bw, "run_maintenance", lambda *a, **k: started.append("maintenance") or 0)
    monkeypatch.setattr(bw, "run_monitor", lambda *a, **k: started.append("monitor") or 0)
    assert bw.main(["--mode", "agent", "--install-root", str(tmp_path)]) == bw.EXIT_REFUSED
    assert bw.main(["--mode", "plan", "--install-root", str(tmp_path)]) == 0
    assert bw.main(["--mode", "maintenance", "--install-root", str(tmp_path), "--work-root", str(tmp_path)]) == 0
    assert started == ["plan", "maintenance"]
    assert bw.worker_cap_refusal(_agent(200, 300), 5000, for_mode="plan") == ""
    assert bw.worker_cap_refusal(_agent(200, 300), 5000, for_mode="maintenance") == ""
    assert bw.worker_cap_refusal(_agent(200, 300), 5000, for_mode="agent") != ""


def test_fr2522_startworker_plan_uncapped_agent_capped(tmp_path, monkeypatch):
    import os
    import time as _time
    q = tmp_path / "run" / "startworker"
    q.mkdir(parents=True)
    now = _time.time()
    (q / "tray.alive").write_text("1", encoding="utf-8")
    os.utime(q / "tray.alive", (now - 1.0, now - 1.0))
    gate = sw.StartGate(max_workers=2, cooldown_s=0.0)
    procs = lambda: _agent(100, 200) + [(300, 1, "bob-worker.exe", "plan")]
    monkeypatch.setattr(sw, "count_irc_agent_seats", lambda **kw: 2)

    d_agent = sw.decide(
        body="!startworker agent", nick="simon", account="simon", channel="#box",
        local_machine="box", gate=gate, qdir=q, machine_of_nick=lambda n: "box",
        procs=procs, now=now, write=False,
    )
    assert d_agent and d_agent.ok is False and d_agent.reason == "cap"

    d_plan = sw.decide(
        body="!startworker plan", nick="simon", account="simon", channel="#box",
        local_machine="box", gate=gate, qdir=q, machine_of_nick=lambda n: "box",
        procs=procs, now=now, write=False,
    )
    assert d_plan and d_plan.ok is True and d_plan.mode == "plan"
    assert sw.count_workers(procs()) == 2
    assert sw.count_workers(procs(), modes=("agent", "plan")) == 3
