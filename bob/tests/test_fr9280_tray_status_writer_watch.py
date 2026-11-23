# -*- coding: utf-8 -*-
"""FR #9280: stale tray-status vs fresh tray.alive; starting-stuck; heartbeat skip; dedup."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from repo_layout import ROOT

sys.path.insert(0, str(ROOT / "common" / "scripts"))
import tray_engine_report as ter  # noqa: E402
import tray_status_writer_watch as watch  # noqa: E402

DIALOGS = ROOT / "bob" / "tray" / "tools" / "BobTrayDialogs.ps1"
WATCH = ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
CS = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"
PS = pytest.importorskip("shutil").which("powershell") or "powershell.exe"
WIN = pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell")


def test_fr9280_evaluate_starting_stuck(tmp_path: Path):
    snap = tmp_path / "tray-status.json"
    snap.write_text(json.dumps({"v": 1, "title": "starting", "short": "starting"}), encoding="utf-8")
    alive = tmp_path / "tray.alive"
    alive.write_text("ok", encoding="ascii")
    now = time.time()
    os.utime(snap, (now - 10, now - 10))
    os.utime(alive, (now - 1, now - 1))
    started = now - 200  # past StartingStuckSeconds=180
    assert (
        watch.evaluate_reason(snap, alive, engine_started_epoch=started, now=now)
        == "starting-stuck"
    )


def test_fr9280_evaluate_status_vs_alive(tmp_path: Path):
    snap = tmp_path / "tray-status.json"
    snap.write_text(json.dumps({"v": 1, "short": "Bob: engine up"}), encoding="utf-8")
    alive = tmp_path / "tray.alive"
    alive.write_text("ok", encoding="ascii")
    now = time.time()
    os.utime(snap, (now - 400, now - 400))
    os.utime(alive, (now - 2, now - 2))
    started = now - 500
    assert (
        watch.evaluate_reason(snap, alive, engine_started_epoch=started, now=now)
        == "status-vs-alive"
    )


def test_fr9280_evaluate_ok_when_status_fresh(tmp_path: Path):
    snap = tmp_path / "tray-status.json"
    snap.write_text(json.dumps({"v": 1, "short": "Bob"}), encoding="utf-8")
    alive = tmp_path / "tray.alive"
    alive.write_text("ok", encoding="ascii")
    now = time.time()
    os.utime(snap, (now - 5, now - 5))
    os.utime(alive, (now - 1, now - 1))
    assert watch.evaluate_reason(snap, alive, engine_started_epoch=now - 60, now=now) == ""


def test_fr9280_starting_within_grace_not_stuck(tmp_path: Path):
    snap = tmp_path / "tray-status.json"
    snap.write_text(json.dumps({"short": "starting"}), encoding="utf-8")
    alive = tmp_path / "tray.alive"
    alive.write_text("ok", encoding="ascii")
    now = time.time()
    os.utime(alive, (now - 1, now - 1))
    # 60s after start: still grace for starting-stuck (180s)
    assert watch.evaluate_reason(snap, alive, engine_started_epoch=now - 60, now=now) == ""


def test_fr9280_cs_pins_watch_and_heal():
    t = CS.read_text(encoding="utf-8-sig")
    assert "internal static class TrayStatusWriterWatch" in t
    assert "StartingStuckSeconds = 180" in t
    assert "status-vs-alive" in t
    assert "starting-stuck" in t
    assert "Bob: status stalled" in t
    assert "--status-writer-eval" in t
    assert "TrayStatusWriterWatch.EvaluateReason" in t
    # Must not retarget seats from this path
    heal = t[t.index("void HealEngine()") : t.index("void HealEngine()") + 3500]
    assert "WorkerLauncher" not in heal


def test_fr9280_ps_heartbeat_skips_starting_seed():
    d = DIALOGS.read_text(encoding="utf-8")
    body = d[
        d.index("function Update-BobTrayStatusHeartbeat") : d.index(
            "function Update-BobTrayStatusHeartbeat"
        )
        + 900
    ]
    assert "FR #9280" in body
    assert "starting" in body
    assert "return $null" in body


def test_fr9280_watch_leaves_starting_at_tray_up():
    w = WATCH.read_text(encoding="utf-8")
    assert "FR #9280" in w
    assert "Bob: engine up" in w
    assert w.index("Write-TrayLog 'tray up'") < w.index("Bob: engine up")


def _report_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("BOB_TRAY_ENGINE_REPORT_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("BOB_CRASH_SPOOL", str(tmp_path / "spool"))
    monkeypatch.setenv("BOB_MACHINE_ID", "fr9280box")
    monkeypatch.setenv("BOB_CRASH_REPORT", "1")
    life = tmp_path / "tray-lifecycle.log"
    life.write_text('{"ts":"t","event":"engine-stale"}\n', encoding="utf-8")
    monkeypatch.setenv("BOB_TRAY_LIFECYCLE_LOG", str(life))


def test_fr9280_tray_engine_report_accepts_new_kinds(monkeypatch, tmp_path: Path):
    # Per-machine dedupe (FR #7505): first kind opens; second kind for same mid comments.
    _report_env(monkeypatch, tmp_path)
    posts = []
    comments = []

    def filer_new(title, body, **kw):
        posts.append({"title": title, "body": body})
        return {"ok": True, "number": 1}

    def filer_comment(repo, number, body):
        comments.append(body)
        return True

    a = ter.report(
        "starting-stuck",
        machine="fr9280a",
        find_open=lambda r, s: None,
        filer_new=filer_new,
        filer_comment=filer_comment,
        now_epoch=1_700_000_000.0,
    )
    assert a.get("ok") is True
    assert a.get("kind") == "starting-stuck"
    assert len(posts) == 1
    assert "starting-stuck" in posts[0]["title"]

    b = ter.report(
        "status-vs-alive",
        machine="fr9280a",
        find_open=lambda r, s: 1,
        filer_new=filer_new,
        filer_comment=filer_comment,
        now_epoch=1_700_000_000.0 + 60,
        force_comment=True,
    )
    assert b.get("ok") is True
    assert b.get("kind") == "status-vs-alive"
    assert b.get("deduped") is True
    assert len(posts) == 1
    assert len(comments) == 1
    assert "status-vs-alive" in comments[0]


def test_fr9280_tray_engine_report_dedup_repeat(monkeypatch, tmp_path: Path):
    _report_env(monkeypatch, tmp_path)
    posts = []
    comments = []
    open_n = {"n": None}

    def find_open(repo, sig):
        return open_n["n"]

    def filer_new(title, body, **kw):
        posts.append(title)
        open_n["n"] = 42
        return {"ok": True, "number": 42}

    def filer_comment(repo, number, body):
        comments.append(body)
        return True

    t0 = 1_700_000_000.0
    a = ter.report(
        "status-vs-alive",
        machine="fr9280b",
        find_open=find_open,
        filer_new=filer_new,
        filer_comment=filer_comment,
        now_epoch=t0,
    )
    assert a.get("ok") is True
    assert len(posts) == 1
    b = ter.report(
        "status-vs-alive",
        machine="fr9280b",
        find_open=find_open,
        filer_new=filer_new,
        filer_comment=filer_comment,
        now_epoch=t0 + 60,
    )
    assert b.get("deduped") is True or b.get("rate_limited") is True
    assert len(posts) == 1


@WIN
def test_fr9280_heartbeat_runtime_skips_starting(tmp_path: Path):
    root = tmp_path / "root"
    run = root / "run"
    run.mkdir(parents=True)
    snap = run / "tray-status.json"
    snap.write_text(
        json.dumps({"v": 1, "title": "starting", "short": "starting"}),
        encoding="utf-8",
    )
    old_mtime = time.time() - 100
    os.utime(snap, (old_mtime, old_mtime))
    script = f"""
$ErrorActionPreference = 'Stop'
. '{DIALOGS}'
$r = Update-BobTrayStatusHeartbeat -Root '{root}'
if ($null -ne $r) {{ throw 'expected null skip for starting seed' }}
$m = (Get-Item -LiteralPath '{snap}').LastWriteTimeUtc
Write-Output ('mtime_unchanged=1')
"""
    ps1 = tmp_path / "hb.ps1"
    ps1.write_text(script, encoding="utf-8")
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "mtime_unchanged=1" in r.stdout
    # mtime must not have been refreshed to "now"
    assert abs(snap.stat().st_mtime - old_mtime) < 2.0
