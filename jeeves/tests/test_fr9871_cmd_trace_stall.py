# -*- coding: utf-8 -*-
"""FR #9871: cmd-trace stall while stdout/GIT announce stays fresh."""
from __future__ import annotations

import importlib.util
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "common" / "scripts"
MON = ROOT / "jeeves" / "tools" / "monitor"
sys.path.insert(0, str(SCRIPTS))

import chair_log_freshness as clf  # noqa: E402

INVOKE = ROOT / "jeeves" / "scripts" / "Invoke-JeevesMonitorCheck.ps1"
WRAP = ROOT / "jeeves" / "scripts" / "Test-JeevesMonitorCmdTraceStall.ps1"
AGENTS = ROOT / "jeeves" / "AGENTS.md"
SKILL = ROOT / "jeeves" / ".grok" / "skills" / "monitor-start" / "SKILL.md"
DOCS = ROOT / "jeeves" / "docs" / "monitoring.md"


def _load_monitor():
    spec = importlib.util.spec_from_file_location(
        "cmd_trace_stall_monitor", MON / "cmd_trace_stall.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.path.insert(0, str(MON))
    spec.loader.exec_module(mod)
    return mod


def test_fr9871_wiring():
    inv = INVOKE.read_text(encoding="utf-8")
    assert "cmd_trace_stall" in inv
    assert WRAP.is_file()
    assert "cmd_trace_stall" in WRAP.read_text(encoding="utf-8-sig")
    assert (MON / "cmd_trace_stall.py").is_file()
    agents = AGENTS.read_text(encoding="utf-8")
    assert "cmd_trace_stall" in agents
    assert "9871" in agents
    skill = SKILL.read_text(encoding="utf-8")
    assert "cmd_trace_stall" in skill
    assert "9871" in skill
    docs = DOCS.read_text(encoding="utf-8")
    assert "9871" in docs
    assert "require_machine=walrus" in docs


def test_fr9871_stall_when_cmd_stale_stdout_fresh(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BOB_CMD_TRACE_STALL_S", "60")
    home = tmp_path / "chair"
    home.mkdir()
    install = tmp_path / "jeeves"
    (install / "logs").mkdir(parents=True)
    stdout = install / "logs" / "stdout.log"
    trace = home / "cmd-trace.log"
    now = time.time()
    stdout.write_text("GIT announce still flowing\n", encoding="utf-8")
    trace.write_text("old cmd\n", encoding="utf-8")
    os.utime(stdout, (now, now))
    os.utime(trace, (now - 600, now - 600))
    snap = clf.cmd_trace_stall_snapshot(
        home, now=now, max_age_s=60.0, install_roots=[install]
    )
    assert snap["stalled"] is True
    assert snap["fingerprint"] == clf.STALL_FINGERPRINT
    assert snap["reason"] == "cmd_trace_stale_stdout_fresh"
    assert snap["require_machine_live"] == "walrus"
    # FR #9900 would still say progress_ok because stdout is fresh.
    prog = clf.progress_snapshot(
        home, now=now, max_age_s=60.0, install_roots=[install]
    )
    assert prog["progress_ok"] is True


def test_fr9871_not_stall_when_cmd_fresh(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BOB_CMD_TRACE_STALL_S", "60")
    home = tmp_path / "chair"
    home.mkdir()
    install = tmp_path / "jeeves"
    (install / "logs").mkdir(parents=True)
    stdout = install / "logs" / "stdout.log"
    trace = home / "cmd-trace.log"
    now = time.time()
    stdout.write_text("x\n", encoding="utf-8")
    trace.write_text("fresh\n", encoding="utf-8")
    os.utime(stdout, (now, now))
    os.utime(trace, (now, now))
    snap = clf.cmd_trace_stall_snapshot(
        home, now=now, max_age_s=60.0, install_roots=[install]
    )
    assert snap["stalled"] is False
    assert snap["reason"] == "cmd_fresh"


def test_fr9871_write_fingerprint_and_monitor_finding(tmp_path: Path, monkeypatch):
    m = _load_monitor()
    home = tmp_path / "chair"
    home.mkdir()
    install = tmp_path / "jeeves"
    (install / "logs").mkdir(parents=True)
    stdout = install / "logs" / "stdout.log"
    trace = home / "cmd-trace.log"
    now = time.time()
    stdout.write_text("GIT\n", encoding="utf-8")
    trace.write_text("old\n", encoding="utf-8")
    os.utime(stdout, (now, now))
    os.utime(trace, (now - 999, now - 999))
    monkeypatch.setenv("BOB_CMD_TRACE_STALL_S", "30")
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(install))
    monkeypatch.setattr(m, "_service_state", lambda _n: "Running")
    monkeypatch.setattr(m, "_port_listening", lambda *a, **k: True)
    monkeypatch.setattr(m, "resolve_homes", lambda _args: (home, tmp_path / "digest"))
    args = SimpleNamespace(no_heal=False)
    payload, code = m.check(args)
    assert code == 1
    assert payload["stalled"] is True
    assert any("9871" in f for f in payload["findings"])
    assert payload["heal"] and payload["heal"].get("stamp")
    stamp = Path(payload["heal"]["stamp"])
    assert stamp.is_file()
    assert "cmd_trace_stall" in stamp.read_text(encoding="utf-8")
    assert payload["require_machine_live"] == "walrus"
