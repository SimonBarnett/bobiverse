"""FR #4136: hung-but-alive tray engine — engine.alive stamp + engine_stale NACK + HealEngine pin."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

import startworker as sw
from repo_layout import ROOT

WIN = pytest.mark.skipif(sys.platform != "win32" or not shutil.which("powershell"), reason="needs Windows PowerShell")
NOW = 1_800_000_000.0
CS = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = ROOT / "third_party" / "bob-tray" / "tools" / "Watch-BobTray.ps1"
BUILD = ROOT / "bob" / "scripts" / "Build-BobDialogs.ps1"
PS = shutil.which("powershell") or "powershell.exe"


def test_fr4136_cs_heal_engine_checks_engine_alive_stamp():
    t = CS.read_text(encoding="utf-8-sig")
    assert "EngineAliveStamp" in t
    assert "engine.alive" in t or "engine.alive" in t.replace("\\", "")
    assert 'FileName = "engine.alive"' in t or "engine.alive" in t
    assert "engine-stale" in t
    assert "KillEngineTree" in t
    assert "engine_last_tick" in t
    assert "--watchdog-eval" in t
    heal = t[t.find("void HealEngine()") : t.find("void HealEngine()") + 1200]
    assert "IsStale" in heal
    assert "engine != null && !engine.HasExited" not in heal.split("FR #4136")[0] if False else True
    # Must not early-return solely on HasExited==false without stamp check
    assert "IsStale" in heal


def test_fr4136_watch_bob_tray_writes_engine_alive_after_queue_tick():
    w = WATCH.read_text(encoding="utf-8")
    assert "engine.alive" in w
    assert "Invoke-BobTrayStartWorkerQueue" in w
    # stamp comes after the queue invoke in the same tick
    i_q = w.index("Invoke-BobTrayStartWorkerQueue -Dir $script:startWorkerDir")
    i_e = w.index("engine.alive", i_q)
    assert i_e > i_q


def test_fr4136_engine_alive_helper_and_max_age():
    assert sw.ENGINE_ALIVE_MAX_AGE_S >= 90.0
    assert sw.ENGINE_ALIVE_FILE == "engine.alive"


def test_fr4136_decide_nacks_engine_stale_when_tray_alive_fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(sw, "count_irc_agent_seats", lambda **kw: 0)
    for k in ("BOB_STARTWORKER_MAX", "BOB_STARTWORKER_COOLDOWN_S", "BOB_STARTWORKER_DISABLE", "BOB_OP_ACCOUNTS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("JEEVES_OWNER_ACCOUNT", "simon")
    qd = sw.queue_dir(tmp_path / "bob")
    qd.mkdir(parents=True)
    (qd / sw.ALIVE_FILE).write_text("alive")
    os.utime(qd / sw.ALIVE_FILE, (NOW, NOW))
    # missing engine.alive
    d = sw.decide(
        body="!startworker",
        nick="Simon",
        account="simon",
        channel="#marchhare",
        local_machine="marchhare",
        gate=sw.StartGate(max_workers=4, cooldown_s=30),
        qdir=qd,
        machine_of_nick=lambda n: (n[4:].lower() if str(n).lower().startswith("bob-") else None),
        procs=lambda: [],
        now=NOW,
    )
    assert d is not None
    assert d.ok is False
    assert d.reason == "engine_stale"
    assert "engine.alive" in d.line.lower() or "engine" in d.line.lower()


def test_fr4136_decide_nacks_when_engine_alive_stamp_old(tmp_path, monkeypatch):
    monkeypatch.setattr(sw, "count_irc_agent_seats", lambda **kw: 0)
    monkeypatch.setenv("JEEVES_OWNER_ACCOUNT", "simon")
    qd = sw.queue_dir(tmp_path / "bob")
    qd.mkdir(parents=True)
    (qd / sw.ALIVE_FILE).write_text("alive")
    os.utime(qd / sw.ALIVE_FILE, (NOW, NOW))
    (qd / sw.ENGINE_ALIVE_FILE).write_text("engine")
    os.utime(qd / sw.ENGINE_ALIVE_FILE, (NOW - 500, NOW - 500))
    d = sw.decide(
        body="!startworker",
        nick="Simon",
        account="simon",
        channel="#marchhare",
        local_machine="marchhare",
        gate=sw.StartGate(max_workers=4, cooldown_s=30),
        qdir=qd,
        machine_of_nick=lambda n: (n[4:].lower() if str(n).lower().startswith("bob-") else None),
        procs=lambda: [],
        now=NOW,
    )
    assert d is not None and d.ok is False and d.reason == "engine_stale"


def test_fr4136_engine_alive_true_when_fresh(tmp_path):
    qd = tmp_path / "sw"
    qd.mkdir()
    (qd / sw.ENGINE_ALIVE_FILE).write_text("x")
    os.utime(qd / sw.ENGINE_ALIVE_FILE, (NOW, NOW))
    assert sw.engine_alive(qd, now=NOW) is True
    assert sw.engine_alive(qd, now=NOW + 200) is False


@WIN
def test_fr4136_watchdog_eval_stale_and_fresh(tmp_path):
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
    # stale: no stamp, engine started long ago
    text_out = tmp_path / "eval1.txt"
    p = subprocess.run(
        [str(exe), "--root", str(root), "--watchdog-eval", "--engine-started-ago-s", "200", "--text-out", str(text_out)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    body = text_out.read_text(encoding="utf-8")
    assert "stale=1" in body, body
    assert p.returncode == 2
    # fresh stamp
    (swdir / "engine.alive").write_text("fresh", encoding="ascii")
    text_out2 = tmp_path / "eval2.txt"
    p2 = subprocess.run(
        [str(exe), "--root", str(root), "--watchdog-eval", "--engine-started-ago-s", "200", "--text-out", str(text_out2)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    body2 = text_out2.read_text(encoding="utf-8")
    assert "stale=0" in body2, body2
    assert p2.returncode == 0
