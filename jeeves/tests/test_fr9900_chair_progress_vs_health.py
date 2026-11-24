# -*- coding: utf-8 -*-
"""FR #9900: chair log freshness distinct from /health ok."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "common" / "scripts"
MON = ROOT / "jeeves" / "tools" / "monitor"
sys.path.insert(0, str(SCRIPTS))

import bobcallback  # noqa: E402
import chair_log_freshness as clf  # noqa: E402

INVOKE = ROOT / "jeeves" / "scripts" / "Invoke-JeevesMonitorCheck.ps1"
WRAP = ROOT / "jeeves" / "scripts" / "Test-JeevesMonitorChairProgress.ps1"
AGENTS = ROOT / "jeeves" / "AGENTS.md"
SKILL = ROOT / "jeeves" / ".grok" / "skills" / "monitor-start" / "SKILL.md"


def _load_monitor():
    spec = importlib.util.spec_from_file_location(
        "chair_progress_monitor", MON / "chair_progress.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # Ensure monitor can import _common from MON
    sys.path.insert(0, str(MON))
    spec.loader.exec_module(mod)
    return mod


def test_fr9900_wiring():
    inv = INVOKE.read_text(encoding="utf-8")
    assert "chair_progress" in inv
    assert WRAP.is_file()
    assert "chair_progress" in WRAP.read_text(encoding="utf-8-sig")
    assert (MON / "chair_progress.py").is_file()
    assert (SCRIPTS / "chair_log_freshness.py").is_file()
    agents = AGENTS.read_text(encoding="utf-8")
    assert "chair_progress" in agents
    assert "9900" in agents
    skill = SKILL.read_text(encoding="utf-8")
    assert "chair_progress" in skill
    assert "9900" in skill


def test_fr9900_snapshot_stale_vs_fresh(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BOB_CHAIR_PROGRESS_MAX_AGE_S", "60")
    home = tmp_path / "chair"
    home.mkdir()
    install = tmp_path / "jeeves"
    (install / "logs").mkdir(parents=True)
    stdout = install / "logs" / "stdout.log"
    trace = home / "cmd-trace.log"
    now = time.time()
    stdout.write_text("old\n", encoding="utf-8")
    trace.write_text("old\n", encoding="utf-8")
    old = now - 120
    os.utime(stdout, (old, old))
    os.utime(trace, (old, old))
    snap = clf.progress_snapshot(
        home, now=now, max_age_s=60.0, install_roots=[install]
    )
    assert snap["progress_ok"] is False
    assert snap["progress_reason"] == "stale_logs"
    assert snap["stdout_age_s"] >= 60
    stdout.write_text("new\n", encoding="utf-8")
    os.utime(stdout, (now, now))
    snap2 = clf.progress_snapshot(
        home, now=now, max_age_s=60.0, install_roots=[install]
    )
    assert snap2["progress_ok"] is True
    assert snap2["progress_reason"] == "fresh"


def test_fr9900_health_includes_progress_fields(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BOB_CHAIR_PROGRESS_MAX_AGE_S", "30")
    home = tmp_path / "cb"
    home.mkdir()
    (home / "cmd-trace.log").write_text("x\n", encoding="utf-8")
    code, raw = bobcallback.handle_health_get(home)
    assert code == 200
    doc = json.loads(raw.decode("utf-8"))
    assert "progress_ok" in doc
    assert "progress_max_age_s" in doc
    assert "cmd_trace_age_s" in doc
    assert doc["ok"] is True
    assert "last_digest_write" in doc


def test_fr9900_monitor_finding_when_health_ok_logs_stale(tmp_path: Path, monkeypatch):
    m = _load_monitor()
    home = tmp_path / "chair"
    home.mkdir()
    monkeypatch.setenv("BOB_CHAIR_PROGRESS_MAX_AGE_S", "60")
    monkeypatch.setattr(m, "_service_state", lambda _n: "Running")
    monkeypatch.setattr(m, "_port_listening", lambda *a, **k: True)
    monkeypatch.setattr(
        m,
        "probe_local_health",
        lambda *a, **k: (
            True,
            {
                "ok": True,
                "progress_ok": False,
                "progress_reason": "stale_logs",
                "stdout_age_s": 7200,
                "cmd_trace_age_s": None,
                "progress_max_age_s": 60,
            },
        ),
    )
    monkeypatch.setattr(m, "resolve_homes", lambda _args: (home, tmp_path / "digest"))
    payload, code = m.check(SimpleNamespace(dry_run=False))
    assert code == m.EXIT_FINDING
    assert payload["ok"] is False
    assert any("9900" in f for f in payload["findings"])


def test_fr9900_monitor_ok_when_progress_fresh(tmp_path: Path, monkeypatch):
    m = _load_monitor()
    home = tmp_path / "chair"
    home.mkdir()
    monkeypatch.setattr(m, "_service_state", lambda _n: "Running")
    monkeypatch.setattr(m, "_port_listening", lambda *a, **k: True)
    monkeypatch.setattr(
        m,
        "probe_local_health",
        lambda *a, **k: (
            True,
            {
                "ok": True,
                "progress_ok": True,
                "progress_reason": "fresh",
                "stdout_age_s": 5,
                "cmd_trace_age_s": 5,
                "progress_max_age_s": 1800,
            },
        ),
    )
    monkeypatch.setattr(m, "resolve_homes", lambda _args: (home, tmp_path / "digest"))
    payload, code = m.check(SimpleNamespace(dry_run=False))
    assert code == m.EXIT_OK
    assert payload["ok"] is True
    assert payload["findings"] == []
