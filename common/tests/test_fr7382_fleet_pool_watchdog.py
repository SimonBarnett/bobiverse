"""FR #7382: fleet pool watchdog pokes cadence without ChairJobs.tick / outbox drain."""
from __future__ import annotations

import threading
from pathlib import Path

import bobreport
import chair_health as ch
import fleet_pool_fetch as fp


NOW = 1_700_000_000.0


class Clock:
    def __init__(self, t: float = NOW):
        self.t = float(t)

    def __call__(self) -> float:
        return self.t


def _jobs(tmp_path: Path, clk: Clock, *, spawn: bool = False, logs=None):
    bobreport.save_digest(tmp_path, bobreport.empty_digest())
    return ch.ChairJobs(
        tmp_path,
        tmp_path,
        log=(logs.append if logs is not None else (lambda *_a, **_k: None)),
        announce=lambda *_a, **_k: None,
        http=lambda *a, **k: 200,
        fetch_json=lambda url: [],
        token_loader=lambda: (None, "missing"),
        clock=clk,
        sleep=lambda _s: None,
        spawn=spawn,
        owners={"SimonBarnett"},
    )


def test_fr7382_watchdog_interval_constant():
    assert 0.2 <= ch.FLEET_POOL_WATCH_S <= 2.0


def test_fr7382_maybe_tick_without_chair_tick(tmp_path: Path, monkeypatch):
    """Cadence must run when nobody calls tick() (outbox drain blocked)."""
    clk = Clock(NOW)
    hits: list[float] = []

    def fake_tick(home, *, now=None, force=False, **_kw):
        hits.append(float(now if now is not None else clk()))
        return {}

    monkeypatch.setattr(fp, "tick_fleet_pools", fake_tick)
    j = _jobs(tmp_path, clk, spawn=False)
    j.next_fleet_pool = NOW
    j._maybe_tick_fleet_pools()
    assert hits == [NOW]


def test_fr7382_spawn_starts_watchdog_thread(tmp_path: Path):
    clk = Clock(NOW)
    j = _jobs(tmp_path, clk, spawn=True)
    try:
        th = j._fleet_watchdog_thread
        assert th is not None
        assert th.daemon
        assert th.name == "fleet-pool-watch"
        assert th.is_alive()
        src = Path(ch.__file__).read_text(encoding="utf-8")
        assert "_fleet_pool_watchdog_loop" in src
        assert "FLEET_POOL_WATCH_S" in src
    finally:
        j._fleet_watchdog_stop.set()
        th.join(timeout=3.0)


def test_fr7382_spawn_false_does_not_start_watchdog(tmp_path: Path):
    j = _jobs(tmp_path, Clock(NOW), spawn=False)
    assert j._fleet_watchdog_thread is None
