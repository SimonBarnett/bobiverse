"""FR #9236: listener self-exit logs free memory; low-mem backs off instead of crash-looping.

Deduplicated intake carries free_mb. No machine names.
"""
from __future__ import annotations

import json
from pathlib import Path

import bobcallback


def test_fr9236_self_probe_exit_includes_free_mem_in_report(monkeypatch):
    reports: list[dict] = []
    exits: list[int] = []

    monkeypatch.setattr(
        bobcallback,
        "probe_listener_local_get",
        lambda url, timeout_s: (_ for _ in ()).throw(TimeoutError("probe-timeout")),
    )
    monkeypatch.setattr(bobcallback, "free_memory_mb", lambda: 12000.0)

    bobcallback.listener_self_probe_tick(
        host="127.0.0.1",
        port=9,
        timeout_s=1.0,
        fail_streak=0,
        max_fails=1,
        report_fn=lambda **kw: reports.append(kw) or {"ok": True},
        exit_fn=lambda code: exits.append(int(code)),
        sleeper=lambda _s: None,
    )

    assert exits == [1]
    assert len(reports) == 1
    assert reports[0].get("free_mb") == 12000.0 or "free_mb" in json.dumps(reports[0])
    body = json.dumps(reports[0]).lower()
    assert "password" not in body
    assert "secret" not in body or "no secrets" in body


def test_fr9236_low_mem_backs_off_without_exit(monkeypatch):
    """When free memory is below the threshold, do not exit; back off and keep streak soft."""
    reports: list[dict] = []
    exits: list[int] = []
    sleeps: list[float] = []
    defer_box = [0]

    monkeypatch.setattr(
        bobcallback,
        "probe_listener_local_get",
        lambda url, timeout_s: (_ for _ in ()).throw(
            ConnectionRefusedError("connection refused")
        ),
    )
    monkeypatch.setattr(bobcallback, "free_memory_mb", lambda: 180.0)
    monkeypatch.setenv("BOB_CALLBACK_LOW_MEM_MB", "512")
    monkeypatch.setenv("BOB_CALLBACK_LOW_MEM_BACKOFF_S", "0.01")
    monkeypatch.setenv("BOB_CALLBACK_LOW_MEM_MAX_DEFER", "3")

    streak = bobcallback.listener_self_probe_tick(
        host="127.0.0.1",
        port=9,
        timeout_s=1.0,
        fail_streak=0,
        max_fails=1,
        report_fn=lambda **kw: reports.append(kw) or {"ok": True},
        exit_fn=lambda code: exits.append(int(code)),
        sleeper=lambda s: sleeps.append(float(s)),
        defer_box=defer_box,
    )

    assert exits == []
    assert sleeps, "expected a low-mem backoff sleep"
    # Soften streak to max_fails-1 so the next tick re-evaluates (here max_fails=1 -> 0).
    assert streak == 0
    assert defer_box[0] == 1
    assert reports == []  # intake only on real exit


def test_fr9236_low_mem_eventually_exits_with_intake(monkeypatch):
    reports: list[dict] = []
    exits: list[int] = []
    defer_box = [0]
    fail_streak = 0

    monkeypatch.setattr(
        bobcallback,
        "probe_listener_local_get",
        lambda url, timeout_s: (_ for _ in ()).throw(TimeoutError("still-dead")),
    )
    monkeypatch.setattr(bobcallback, "free_memory_mb", lambda: 90.0)
    monkeypatch.setenv("BOB_CALLBACK_LOW_MEM_MB", "512")
    monkeypatch.setenv("BOB_CALLBACK_LOW_MEM_BACKOFF_S", "0")
    monkeypatch.setenv("BOB_CALLBACK_LOW_MEM_MAX_DEFER", "2")

    for _ in range(5):
        fail_streak = bobcallback.listener_self_probe_tick(
            host="127.0.0.1",
            port=9,
            timeout_s=1.0,
            fail_streak=fail_streak,
            max_fails=1,
            report_fn=lambda **kw: reports.append(kw) or {"ok": True},
            exit_fn=lambda code: exits.append(int(code)),
            sleeper=lambda _s: None,
            defer_box=defer_box,
        )
        if exits:
            break

    assert exits == [1]
    assert len(reports) == 1
    assert reports[0].get("why") in {"self-probe", "low-memory", "self-probe-low-memory"}
    assert float(reports[0].get("free_mb") or 0) == 90.0 or "90" in json.dumps(reports[0])


def test_fr9236_accept_fatal_logs_free_mem(monkeypatch, capsys):
    class Boom:
        server_address = ("127.0.0.1", 7700)

        def serve_forever(self):
            raise MemoryError("fr9236-injected")

        def server_close(self):
            return None

    reports: list = []
    exits: list[int] = []
    monkeypatch.setattr(bobcallback, "free_memory_mb", lambda: 200.0)

    bobcallback.serve_forever_guarded(
        Boom(),
        report_fn=lambda exc: reports.append(type(exc).__name__),
        exit_fn=lambda code: exits.append(int(code)),
    )
    captured = capsys.readouterr().out
    assert "MemoryError" in captured or reports == ["MemoryError"]
    assert "free_mb=" in captured or "free_mb" in captured.lower()
    assert exits == [1]


def test_fr9236_source_has_no_machine_names():
    root = Path(__file__).resolve().parents[2]
    src = (root / "common" / "scripts" / "bobcallback.py").read_text(encoding="utf-8")
    assert "free_memory_mb" in src
    assert "FR #9236" in src
    banned = ("wal" + "rus", "red" + "queen", "ion" + "os", "flam" + "ingo")
    chunk_start = src.index("def free_memory_mb")
    chunk = src[chunk_start : chunk_start + 4000].lower()
    for name in banned:
        assert name not in chunk
    self_src = Path(__file__).read_text(encoding="utf-8").lower()
    for name in banned:
        assert name not in self_src
