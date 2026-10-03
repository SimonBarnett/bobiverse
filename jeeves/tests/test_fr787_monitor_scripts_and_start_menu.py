"""FR #787: self-harvest + token-free monitor scripts + Start Jeeves Monitor butler shortcut."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import REPO, ROOT

JEEVES = REPO / "jeeves"
AGENTS = JEEVES / "AGENTS.md"
MONITOR_SKILL = JEEVES / ".grok" / "skills" / "bobiverse-jeeves-monitor" / "SKILL.md"
MONITOR_DIR = JEEVES / "tools" / "monitor"
SCRIPTS = JEEVES / "scripts"
BUTLER = JEEVES / "assets" / "jeeves-butler.ico"
BW = REPO / "bob" / "scripts" / "bob_worker.py"

CHECKS = (
    "health",
    "idle_seats",
    "queue_flow",
    "stale_digest",
    "giveup_loops",
    "stuck_accepted",
    "auto_feed",
    "auto_focus",
)
PS_WRAPPERS = (
    "Test-JeevesMonitorHealth.ps1",
    "Test-JeevesMonitorIdleSeats.ps1",
    "Test-JeevesMonitorQueueFlow.ps1",
    "Test-JeevesMonitorStaleDigest.ps1",
    "Test-JeevesMonitorGiveupLoops.ps1",
    "Test-JeevesMonitorStuckAccepted.ps1",
    "Test-JeevesMonitorAutoFeed.ps1",
    "Test-JeevesMonitorAutoFocus.ps1",
    "Invoke-JeevesMonitorCheck.ps1",
    "Start-JeevesMonitor.ps1",
)

WIN = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("powershell"),
    reason="needs Windows PowerShell",
)


def test_butler_ico_exists_and_is_not_bob_systray():
    assert BUTLER.is_file() and BUTLER.stat().st_size > 100
    bob = ROOT / "third_party" / "bob-tray" / "assets" / "bob-systray.ico"
    if bob.is_file():
        assert BUTLER.read_bytes() != bob.read_bytes()


def test_monitor_python_and_ps_wrappers_exist():
    assert (MONITOR_DIR / "_common.py").is_file()
    for name in CHECKS:
        assert (MONITOR_DIR / f"{name}.py").is_file(), name
    for name in PS_WRAPPERS:
        assert (SCRIPTS / name).is_file(), name


@pytest.mark.parametrize("name", CHECKS)
def test_monitor_script_help_and_dry_run(name):
    py = MONITOR_DIR / f"{name}.py"
    help_r = subprocess.run(
        [sys.executable, str(py), "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(MONITOR_DIR),
    )
    assert help_r.returncode == 0, help_r.stderr
    assert "--dry-run" in help_r.stdout
    dry = subprocess.run(
        [sys.executable, str(py), "--dry-run"],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(MONITOR_DIR),
    )
    assert dry.returncode == 0, dry.stderr
    line = dry.stdout.strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["check"] == name


def test_agents_and_monitor_skill_name_scripts_and_self_harvest():
    agents = AGENTS.read_text(encoding="utf-8-sig")
    skill = MONITOR_SKILL.read_text(encoding="utf-8-sig")
    for blob in (agents, skill):
        assert "Prefer token-free" in blob or "token-free" in blob.lower()
        assert "Self-harvest" in blob or "self-harvest" in blob.lower()
        assert "Invoke-BobiverseHarvest.ps1" in blob
        assert "Any repeated manual check becomes such a script" in blob or "repeated manual check" in blob.lower()
        for w in (
            "Test-JeevesMonitorHealth",
            "Test-JeevesMonitorIdleSeats",
            "Test-JeevesMonitorQueueFlow",
            "Test-JeevesMonitorStaleDigest",
            "Test-JeevesMonitorGiveupLoops",
            "Test-JeevesMonitorStuckAccepted",
            "Test-JeevesMonitorAutoFeed",
            "Test-JeevesMonitorAutoFocus",
            "Start Jeeves Monitor",
        ):
            assert w in blob, w


def test_bob_worker_has_monitor_mode_never_resume():
    t = BW.read_text(encoding="utf-8-sig")
    assert '"monitor"' in t or "'monitor'" in t
    assert "def run_monitor" in t
    assert "def monitor_prompt" in t
    assert "--work-root" in t
    assert re.search(r"(?i)never resume", t)
    # dry-run path includes monitor cwd
    assert 'args.mode == "monitor"' in t


def test_start_jeeves_monitor_ps1_never_resume_and_uses_bob_worker():
    t = (SCRIPTS / "Start-JeevesMonitor.ps1").read_text(encoding="utf-8-sig")
    assert "bob-worker" in t
    assert "--mode" in t and "monitor" in t
    assert "--work-root" in t
    assert "--resume" not in t.lower()
    assert "Never resume" in t or "never resume" in t.lower()


@WIN
def test_pack_stages_monitor_tools_butler_and_start_script(tmp_path):
    out = tmp_path / "dist"
    run = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "scripts" / "Pack-BobiverseRelease.ps1"),
            "-Product",
            "jeeves",
            "-SkipMsi",
            "-KeepStage",
            "-SkipWorkerExe",
            "-OutDir",
            str(out),
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert run.returncode == 0, (run.stdout[-2500:] + run.stderr[-2500:])
    ver = (ROOT / "src" / "VERSION").read_text(encoding="utf-8").strip()
    stage = out / f"jeeves-{ver}"
    assert stage.is_dir(), list(out.iterdir())
    assert (stage / "assets" / "jeeves-butler.ico").is_file()
    assert (stage / "scripts" / "Start-JeevesMonitor.ps1").is_file()
    for name in CHECKS:
        assert (stage / "tools" / "monitor" / f"{name}.py").is_file(), name
    for name in PS_WRAPPERS:
        assert (stage / "scripts" / name).is_file(), name
    agents = (stage / "AGENTS.md").read_text(encoding="utf-8-sig")
    assert "Test-JeevesMonitorHealth" in agents
    assert "Self-harvest" in agents or "self-harvest" in agents.lower()
