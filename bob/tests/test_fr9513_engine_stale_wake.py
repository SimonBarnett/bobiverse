"""FR #9513: engine_stale NACK still NACKS, and wakes tray via tray-cmd reload + engine.wake."""
from __future__ import annotations

import os
import time
from pathlib import Path

import startworker as sw


def _fresh_tray(q: Path) -> None:
    q.mkdir(parents=True, exist_ok=True)
    (q / sw.ALIVE_FILE).write_text("tray", encoding="ascii")
    now = time.time()
    os.utime(q / sw.ALIVE_FILE, (now, now))


def test_fr9513_request_engine_wake_writes_reload_and_wake(tmp_path):
    run = tmp_path / "run"
    q = run / "startworker"
    q.mkdir(parents=True)
    assert sw.request_engine_wake(q, now=1_800_000_000.0) is True
    wake = q / sw.ENGINE_WAKE_FILE
    assert wake.is_file()
    cmd = run / "tray-cmd.txt"
    assert cmd.is_file()
    assert "reload" in cmd.read_text(encoding="utf-8").lower()
    # rate limit
    assert sw.request_engine_wake(q, now=1_800_000_010.0) is False
    assert sw.request_engine_wake(q, now=1_800_000_000.0 + sw.ENGINE_WAKE_MIN_INTERVAL_S + 1) is True


def test_fr9513_decide_engine_stale_keeps_nack_and_wakes(tmp_path):
    run = tmp_path / "run"
    q = run / "startworker"
    _fresh_tray(q)
    d = sw.decide(
        body="!startworker agent marchhare",
        nick="Bob-redqueen",
        account="bob-redqueen",
        channel="#bobiverse",
        local_machine="marchhare",
        gate=sw.StartGate(2, 0),
        qdir=q,
        machine_of_nick=lambda n: "redqueen" if "redqueen" in (n or "").lower() else None,
        write=True,
    )
    assert d is not None
    assert d.ok is False
    assert d.reason == "engine_stale"
    assert "wake requested" in d.line
    assert (q / sw.ENGINE_WAKE_FILE).is_file()
    assert "reload" in (run / "tray-cmd.txt").read_text(encoding="utf-8").lower()


def test_fr9513_decide_write_false_skips_wake(tmp_path):
    run = tmp_path / "run"
    q = run / "startworker"
    _fresh_tray(q)
    d = sw.decide(
        body="!startworker agent marchhare",
        nick="Bob-redqueen",
        account="bob-redqueen",
        channel="#bobiverse",
        local_machine="marchhare",
        gate=sw.StartGate(2, 0),
        qdir=q,
        machine_of_nick=lambda n: "redqueen" if "redqueen" in (n or "").lower() else None,
        write=False,
    )
    assert d is not None and d.reason == "engine_stale"
    assert not (q / sw.ENGINE_WAKE_FILE).exists()
    assert not (run / "tray-cmd.txt").exists()

def test_fr9513_tray_has_wake_alert_helper():
    from repo_layout import ROOT
    ps = (ROOT / "bob" / "tray" / "tools" / "BobTrayStartWorker.ps1").read_text(encoding="utf-8-sig")
    assert "Get-BobTrayEngineWakeAlert" in ps
    assert "engine.wake" in ps
    w = (ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1").read_text(encoding="utf-8-sig")
    assert "Get-BobTrayEngineWakeAlert" in w

