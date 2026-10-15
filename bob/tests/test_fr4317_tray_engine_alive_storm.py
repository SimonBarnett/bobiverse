"""FR #4317: HealEngine must not kill-loop on a pre-start leftover engine.alive stamp.

MarchHare 2026-10-15: bob-tray.exe HealEngine (#4136) + frozen engine.alive from 03:36 +
PS that never advanced the stamp -> engine-stale every ~15s, storm window reset every 5 min,
engine restarted forever. Fix: IsStale ignores stamps older than engineStartedUtc; PS seeds
and writes engine.alive at the start of each startworker tick.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from repo_layout import ROOT

WIN = pytest.mark.skipif(sys.platform != "win32" or not shutil.which("powershell"), reason="needs Windows PowerShell")
CS = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
BUILD = ROOT / "bob" / "scripts" / "Build-BobDialogs.ps1"
PS = shutil.which("powershell") or "powershell.exe"


def test_fr4317_is_stale_ignores_pre_start_stamp():
    t = CS.read_text(encoding="utf-8-sig")
    assert "FR #4317" in t
    stale_fn = t[t.find("public static bool IsStale") : t.find("public static bool IsStale") + 1600]
    assert "m < engineStartedUtc" in stale_fn or "m < engineStartedUtc".replace(" ", "") in stale_fn.replace(" ", "")
    assert "return false" in stale_fn
    heal = t[t.find("void HealEngine()") : t.find("void HealEngine()") + 1600]
    assert "engine-restart-storm" in heal
    assert "FR #4317" in heal or "FR #4317" in t


def test_fr4317_watch_seeds_and_writes_engine_alive_before_queue():
    w = WATCH.read_text(encoding="utf-8")
    assert "engine.alive" in w
    assert "FR #4317" in w
    # seed at tray-up
    i_seed_alive = w.index("Write-BobTrayAlive -Dir $script:startWorkerDir")
    i_seed_engine = w.index("engine.alive", i_seed_alive)
    i_tray_up = w.index("Write-TrayLog 'tray up'", i_seed_alive)
    assert i_seed_engine < i_tray_up
    # tick: stamp before queue invoke
    i_tick = w.index("FR #4142: re-entrancy + per-tick timing")
    i_stamp = w.index("engine.alive", i_tick)
    i_q = w.index("Invoke-BobTrayStartWorkerQueue -Dir $script:startWorkerDir", i_tick)
    assert i_stamp < i_q, "engine.alive must be written before the queue invoke in the tick"


@WIN
def test_fr4317_watchdog_eval_pre_start_stamp_not_stale(tmp_path):
    out_dir = tmp_path / "dialogs"
    out_dir.mkdir()
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(BUILD), "-RepoRoot", str(ROOT), "-OutDir", str(out_dir)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    exe = out_dir / "bob-tray.exe"
    assert exe.is_file()
    root = tmp_path / "root"
    swdir = root / "run" / "startworker"
    swdir.mkdir(parents=True)
    # Leftover stamp from hours ago (mtime in the past), engine "started" 30s ago.
    leftover = swdir / "engine.alive"
    leftover.write_text("2026-10-15T02:36:09.3516737Z pid=16368", encoding="ascii")
    past = time.time() - 36000  # 10h ago
    import os

    os.utime(leftover, (past, past))
    text_out = tmp_path / "eval_pre.txt"
    p = subprocess.run(
        [
            str(exe),
            "--root",
            str(root),
            "--watchdog-eval",
            "--engine-started-ago-s",
            "30",
            "--text-out",
            str(text_out),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    body = text_out.read_text(encoding="utf-8")
    assert "stale=0" in body, body
    assert p.returncode == 0

    # Same leftover after grace with no post-start write: still not stale (writer-missing safe).
    text_out2 = tmp_path / "eval_pre2.txt"
    p2 = subprocess.run(
        [
            str(exe),
            "--root",
            str(root),
            "--watchdog-eval",
            "--engine-started-ago-s",
            "200",
            "--text-out",
            str(text_out2),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    body2 = text_out2.read_text(encoding="utf-8")
    assert "stale=0" in body2, body2
    assert p2.returncode == 0

    # Post-start stamp that went cold: still stale (true hang).
    now = time.time()
    leftover.write_text("hung", encoding="ascii")
    os.utime(leftover, (now - 500, now - 500))
    text_out3 = tmp_path / "eval_hung.txt"
    p3 = subprocess.run(
        [
            str(exe),
            "--root",
            str(root),
            "--watchdog-eval",
            "--engine-started-ago-s",
            "600",
            "--text-out",
            str(text_out3),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    body3 = text_out3.read_text(encoding="utf-8")
    assert "stale=1" in body3, body3
    assert p3.returncode == 2
