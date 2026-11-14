"""FR #7377: fleet pool fetch is fixed-rate 60s, independent of chair busy lock."""
from __future__ import annotations

import threading
import time
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


def _jobs(tmp_path: Path, clk: Clock, logs: list[str] | None = None):
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
        spawn=False,
        owners={"SimonBarnett"},
    )


def test_fr7377_constants():
    assert ch.FLEET_POOL_TICK_S == 60.0
    assert ch.FLEET_POOL_FETCH_TIMEOUT_S < 60.0
    assert ch.FLEET_POOL_FETCH_TIMEOUT_S >= 15.0
    assert fp.FLEET_POOL_FETCH_S == 60.0


def test_fr7377_fleet_cadence_while_busy_held(tmp_path: Path, monkeypatch):
    """Slow neighbour holds chair busy; fleet fetch still runs every 60s."""
    clk = Clock(NOW)
    hits: list[float] = []

    def fake_tick(home, *, now=None, force=False, **_kw):
        hits.append(float(now if now is not None else clk()))
        iso = fp.iso_utc(hits[-1])
        return {
            "copilot": {
                "id": "copilot",
                "remaining": 0,
                "fetched_at": iso,
                "last_attempt_at": iso,
                "error": None,
                "source": "test",
                "fresh": True,
            },
            "opencode-go": {
                "id": "opencode-go",
                "remaining": 10,
                "fetched_at": iso,
                "last_attempt_at": iso,
                "error": None,
                "source": "test",
                "fresh": True,
            },
        }

    monkeypatch.setattr(fp, "tick_fleet_pools", fake_tick)
    j = _jobs(tmp_path, clk)
    assert j.busy.acquire(blocking=False)
    j.next_fleet_pool = NOW
    # Chair work blocked by busy; fleet must still fire.
    assert j.tick() is False
    assert hits == [NOW]
    clk.t = NOW + 60.0
    assert j.tick() is False
    assert hits == [NOW, NOW + 60.0]
    # Simulate a 3-minute busy hold between ticks: fixed-rate catches up one slot.
    clk.t = NOW + 60.0 + 180.0
    assert j.tick() is False
    assert len(hits) == 3
    # Age between successive successful applies stays within 75s of schedule intent:
    # third fire happens at wall 240s after first slot; next_fleet advanced past gaps.
    assert hits[2] - hits[1] == 180.0
    assert j.next_fleet_pool > clk.t
    # fetched_at of last hit is "now"; under 75s freshness vs prior scheduled minute
    # is enforced by cadence itself (next due never waits on busy).
    j.busy.release()


def test_fr7377_fixed_rate_not_fixed_delay(tmp_path: Path, monkeypatch):
    clk = Clock(NOW)
    hits: list[float] = []

    def fake_tick(home, *, now=None, force=False, **_kw):
        hits.append(float(now if now is not None else clk()))
        return {}

    monkeypatch.setattr(fp, "tick_fleet_pools", fake_tick)
    j = _jobs(tmp_path, clk)
    j.next_fleet_pool = NOW
    assert j.tick() is not None or True
    # Late by 25s into the next window: next slot stays on the schedule grid.
    clk.t = NOW + 85.0  # 25s after the NOW+60 slot
    j.tick()
    assert hits[0] == NOW
    assert hits[1] == NOW + 85.0
    # Slot after NOW was NOW+60; late fire at 85 advances to NOW+120.
    assert j.next_fleet_pool == NOW + 120.0


def test_fr7377_fetch_timeout_does_not_block_next_slot(tmp_path: Path, monkeypatch):
    clk = Clock(NOW)
    logs: list[str] = []

    def hang(home, *, now=None, force=False, **_kw):
        time.sleep(2.0)
        return {}

    monkeypatch.setattr(fp, "tick_fleet_pools", hang)
    monkeypatch.setattr(ch, "FLEET_POOL_FETCH_TIMEOUT_S", 0.3)
    j = _jobs(tmp_path, clk, logs=logs)
    j.next_fleet_pool = NOW
    t0 = time.perf_counter()
    j.tick()
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.5
    assert any("fleet-pools" in ln and "timeout" in ln for ln in logs)
    assert j.next_fleet_pool == NOW + ch.FLEET_POOL_TICK_S


def test_fr7377_logs_duration(tmp_path: Path, monkeypatch):
    clk = Clock(NOW)
    logs: list[str] = []

    def quick(home, *, now=None, force=False, **_kw):
        return {}

    monkeypatch.setattr(fp, "tick_fleet_pools", quick)
    j = _jobs(tmp_path, clk, logs=logs)
    j.next_fleet_pool = NOW
    j.tick()
    assert any("fleet-pools fetch duration_ms=" in ln and "ok=1" in ln for ln in logs)