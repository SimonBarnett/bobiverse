"""FR #954: monitor-start skill + AGENTS first-turn + Start Jeeves Monitor prompt."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import REPO, ROOT

JEEVES = REPO / "jeeves"
AGENTS = JEEVES / "AGENTS.md"
MONITOR_START = JEEVES / ".grok" / "skills" / "monitor-start" / "SKILL.md"
MONITOR_SKILL = JEEVES / ".grok" / "skills" / "bobiverse-jeeves-monitor" / "SKILL.md"
START_PS1 = JEEVES / "scripts" / "Start-JeevesMonitor.ps1"
BW = REPO / "bob" / "scripts" / "bob_worker.py"
PACK = ROOT / "scripts" / "Pack-BobiverseRelease.ps1"
COMMON = REPO / "common" / "scripts" / "Bobiverse-Common.ps1"

REQUIRED_CHECKS = (
    "health",
    "idle",
    "queue",
    "focus",
    "stale digest",
    "giveup",
    "auto-feed",
    "auto_feed",
    "auto-focus",
    "auto_focus",
)

WIN = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("powershell"),
    reason="needs Windows PowerShell",
)


def test_monitor_start_skill_exists_and_lists_checks():
    assert MONITOR_START.is_file()
    text = MONITOR_START.read_text(encoding="utf-8-sig").lower()
    assert "monitor-start" in text or "first turn" in text
    for needle in (
        "health",
        "idle",
        "queue",
        "focus",
        "stale",
        "giveup",
        "auto",
        "intake",
        ".grok",
        "skills",
    ):
        assert needle in text, needle
    assert "top-level" in text
    assert "no" in text  # "there is no top-level ./skills"
    # Scripts referenced exist
    assert (JEEVES / "scripts" / "Invoke-JeevesMonitorCheck.ps1").is_file()
    assert (JEEVES / "scripts" / "Test-JeevesMonitorHealth.ps1").is_file()
    assert (JEEVES / "tools" / "monitor" / "auto_focus.py").is_file()


def test_agents_md_first_turn_rule_and_grok_skills_path():
    text = AGENTS.read_text(encoding="utf-8-sig")
    assert "monitor-start" in text
    assert re.search(r"(?i)on start.*monitor-start|run the `?monitor-start`? skill NOW", text)
    assert ".grok\\skills" in text or ".grok/skills" in text
    assert re.search(r"(?i)no top-level.*skills|there is \*\*no\*\* top-level", text)
    assert "focus present" in text.lower() or "auto_focus" in text


def test_monitor_skill_points_at_monitor_start():
    text = MONITOR_SKILL.read_text(encoding="utf-8-sig")
    assert "monitor-start" in text
    assert "FR #954" in text or "954" in text


def test_bob_worker_monitor_prompt_runs_monitor_start_now():
    t = BW.read_text(encoding="utf-8-sig")
    assert "def monitor_prompt" in t
    # Extract function body roughly
    m = re.search(r"def monitor_prompt\(.*?\n(.*?)(?=\ndef )", t, re.S)
    assert m, "monitor_prompt not found"
    body = m.group(1)
    assert "monitor-start" in body
    assert re.search(r"(?i)do not wait", body)
    assert "grok" in body and "skills" in body
    assert "never resume" in body.lower() or "NEW session" in body


def test_start_jeeves_monitor_documents_monitor_start():
    t = START_PS1.read_text(encoding="utf-8-sig")
    assert "monitor-start" in t
    assert "never resume" in t.lower()
    assert "--resume" not in t.lower()


def test_shortcut_spec_mentions_monitor_start():
    t = COMMON.read_text(encoding="utf-8-sig")
    assert "Start Jeeves Monitor" in t
    assert "monitor-start" in t


def test_pack_script_stages_monitor_start_for_jeeves():
    t = PACK.read_text(encoding="utf-8-sig")
    assert "monitor-start" in t
    assert "FR #954" in t or "954" in t


@WIN
def test_pack_stages_monitor_start_skill(tmp_path):
    out = tmp_path / "dist"
    run = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PACK),
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
    assert (stage / ".grok" / "skills" / "monitor-start" / "SKILL.md").is_file()
    agents = (stage / "AGENTS.md").read_text(encoding="utf-8-sig")
    assert "monitor-start" in agents
    assert "run the `monitor-start` skill NOW" in agents or "monitor-start skill NOW" in agents
