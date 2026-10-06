"""MRB #2702 hostile: tray.alive off UI thread (FR #2697)."""
from __future__ import annotations

import os
from pathlib import Path

import startworker as sw
from repo_layout import resolve


def test_mrb2702_stale_beyond_max_age_still_nacks(tmp_path):
    q = tmp_path / "startworker"
    q.mkdir()
    f = q / sw.ALIVE_FILE
    f.write_text("alive", encoding="ascii")
    now = 2_000_000.0
    os.utime(f, (now - (sw.TRAY_ALIVE_MAX_AGE_S + 1.0), now - (sw.TRAY_ALIVE_MAX_AGE_S + 1.0)))
    assert sw.tray_alive(q, now=now) is False
    os.utime(f, (now - (sw.TRAY_ALIVE_MAX_AGE_S - 1.0), now - (sw.TRAY_ALIVE_MAX_AGE_S - 1.0)))
    assert sw.tray_alive(q, now=now) is True


def test_mrb2702_max_age_covers_observed_11s_stall_with_margin():
    # Evidence: worst stall ~10.89s; max age must remain > that even without host timer.
    assert sw.TRAY_ALIVE_MAX_AGE_S > 11.0
    assert sw.TRAY_ALIVE_MAX_AGE_S >= 2.0 * 11.0


def test_mrb2702_cs_alive_timer_is_threading_not_winforms():
    cs = resolve("bob/tray/dialogs/BobTray.cs").read_text(encoding="utf-8-sig")
    assert "aliveTimer = new System.Threading.Timer" in cs
    assert "WriteTrayAlive" in cs
    assert "StopAliveTimer" in cs
    # Dispose/delete on exit so a dead host does not leave a fresh-looking file forever.
    assert "File.Delete(aliveFile)" in cs or 'File.Delete(aliveFile)' in cs


def test_mrb2702_ps_heartbeat_not_on_startworker_winforms_tick():
    w = resolve("bob/tray/tools/Watch-BobTray.ps1").read_text(encoding="utf-8-sig")
    # Dedicated ThreadPool timer.
    assert "$script:trayAliveTimer = New-Object System.Timers.Timer" in w
    assert "$script:trayAliveTimer.SynchronizingObject = $null" in w
    # startWorkerTimer tick consumes queue; must not be the sole alive writer.
    i = w.index("$startWorkerTimer.Add_Tick({")
    j = w.index("})", i)
    tick = w[i:j]
    assert "Invoke-BobTrayStartWorkerQueue" in tick
    # Alive primary path is the Elapsed action on trayAliveTimer.
    assert "Register-ObjectEvent -InputObject $script:trayAliveTimer -EventName Elapsed" in w


def test_mrb2702_queue_helper_still_seeds_alive_but_docs_mention_threadpool():
    helper = resolve("bob/tray/tools/BobTrayStartWorker.ps1").read_text(encoding="utf-8-sig")
    assert "FR #2697" in helper
    assert "ThreadPool" in helper or "host timer" in helper
    assert "function Write-BobTrayAlive" in helper
