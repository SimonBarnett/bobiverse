"""FR #9879: !bored is a push event via inbound-transcript tail; never 5-minute timer assign."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import REPO

JEEVES = REPO / "jeeves"
SCRIPTS = JEEVES / "scripts"
WATCH = SCRIPTS / "watch_bored_push_notify.ps1"
ENSURE = SCRIPTS / "Ensure-BoredPushNotify.ps1"
START = SCRIPTS / "Start-JeevesMonitor.ps1"
MONITOR_START = JEEVES / ".grok" / "skills" / "monitor-start" / "SKILL.md"
MONITOR_SKILL = JEEVES / ".grok" / "skills" / "bobiverse-jeeves-monitor" / "SKILL.md"
DOCS = JEEVES / "docs" / "monitoring.md"

WIN = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("powershell"),
    reason="needs Windows PowerShell",
)


def test_watch_bored_push_notify_script_exists_and_is_push_not_timer():
    assert WATCH.is_file(), "productize watch_bored_push_notify.ps1 under jeeves/scripts"
    text = WATCH.read_text(encoding="utf-8-sig")
    assert "inbound-transcript" in text.lower() or "inbound-transcript.log" in text
    assert re.search(r"(?i)PollSec\s*=\s*1|-\s*PollSec.*\b1\b|default.*\b1\b", text) or (
        "PollSec" in text and "1" in text
    )
    assert "!bored" in text or "bored" in text.lower()
    assert re.search(r"(?i)worker ready", text)
    assert re.search(r"(?i)\bDONE\b", text)
    # Must not schedule assign on a 5-minute timer (prohibition prose is OK).
    assert not re.search(
        r"(?i)(every\s+5\s*-?\s*min\w*\s+(assign|offer)|Start-Sleep\s+-Seconds\s+300.*assign|assign.*=\s*300)",
        text,
    )
    assert re.search(r"(?i)must not own assign|health-only|health only", text)
    assert "FR #9879" in text or "9879" in text


def test_ensure_bored_push_dedupes_pids():
    assert ENSURE.is_file(), "Ensure-BoredPushNotify.ps1 must dedupe notifier PIDs"
    text = ENSURE.read_text(encoding="utf-8-sig")
    assert "watch_bored_push_notify" in text
    assert "Get-CimInstance" in text or "Win32_Process" in text
    assert re.search(r"(?i)dedup|already|singleton|extras|keep", text)
    assert "FR #9879" in text or "9879" in text


def test_start_jeeves_monitor_starts_bored_push_notifier():
    text = START.read_text(encoding="utf-8-sig")
    assert "Ensure-BoredPushNotify" in text or "watch_bored_push_notify" in text
    assert "9879" in text


def test_monitor_start_skill_push_not_five_minute_assign():
    text = MONITOR_START.read_text(encoding="utf-8-sig")
    assert "9879" in text
    assert re.search(r"(?i)bored.?push|watch_bored_push_notify|inbound-transcript", text)
    assert re.search(r"(?i)health-only|health only|not own assign|never.*5.?min.*assign", text)
    # Still has a health sleep, but assign must be push-driven
    assert re.search(r"(?i)same turn|push", text)


def test_monitor_skill_and_docs_cover_bored_push():
    skill = MONITOR_SKILL.read_text(encoding="utf-8-sig")
    docs = DOCS.read_text(encoding="utf-8-sig")
    for blob, label in ((skill, "monitor skill"), (docs, "monitoring.md")):
        assert "9879" in blob, label
        assert re.search(r"(?i)bored.?push|watch_bored_push_notify", blob), label
        assert re.search(r"(?i)inbound-transcript|1s poll|poll.?1", blob), label


@WIN
def test_watch_bored_push_parses_fixture_events(tmp_path: Path):
    inbound = tmp_path / "inbound-transcript.log"
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    inbound.write_text(
        "\n".join(
            [
                "#redqueen redqueen-1234 worker ready",
                "#flamingo flamingo-99 DONE FR SimonBarnett/bobiverse#1 https://example.invalid/1",
                "#marchhare marchhare-7 !bored",
                "#bobiverse Jeeves: noise",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    run = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(WATCH),
            "-Inbound",
            str(inbound),
            "-StateDir",
            str(state_dir),
            "-PollSec",
            "1",
            "-MaxEvents",
            "3",
            "-AllowSecondInstance",
            "-StartAtBeginning",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    out = (run.stdout or "") + (run.stderr or "")
    assert run.returncode == 0, out
    assert re.search(r"(?i)READY.*redqueen-1234", out)
    assert re.search(r"(?i)DONE.*flamingo-99", out)
    assert re.search(r"(?i)BORED.*marchhare-7", out)
    events = state_dir / "bored-push-events.log"
    assert events.is_file()
    ev = events.read_text(encoding="utf-8-sig")
    assert "READY" in ev and "DONE" in ev and "BORED" in ev


@WIN
def test_ensure_dry_run_reports_without_spawn(tmp_path: Path):
    run = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ENSURE),
            "-DryRun",
            "-StateDir",
            str(tmp_path / "state"),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    out = (run.stdout or "") + (run.stderr or "")
    assert run.returncode == 0, out
    payload = None
    for line in (run.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("{") and "ok" in line:
            payload = json.loads(line)
    assert payload is not None, out
    assert payload.get("ok") is True
    assert payload.get("check") == "bored_push_notify" or payload.get("dry_run") is True
