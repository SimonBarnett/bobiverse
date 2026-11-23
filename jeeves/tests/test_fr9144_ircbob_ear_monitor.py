# -*- coding: utf-8 -*-
"""FR #9144: ircbob_ear monitor — ear-offline / stale lastSeen / dry-run."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MONITOR = ROOT / "tools" / "monitor" / "ircbob_ear.py"
INVOKE = ROOT / "scripts" / "Invoke-JeevesMonitorCheck.ps1"


def _run(digest_home: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["BOB_DIGEST_HOME"] = str(digest_home)
    env["JEEVES_HOME"] = str(digest_home / "jeeves-home")
    (digest_home / "jeeves-home").mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(MONITOR), "--digest-home", str(digest_home), *extra]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)


def test_fr9144_dry_run_ok(tmp_path: Path):
    r = _run(tmp_path, "--dry-run")
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout.strip().splitlines()[-1])
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["check"] == "ircbob_ear"


def test_fr9144_finding_when_machine_offline(tmp_path: Path):
    now = datetime.now(timezone.utc)
    digest = {
        "ts": now.isoformat().replace("+00:00", "Z"),
        "machines": {
            "redqueen": {
                "online": False,
                "status": "I am offline",
                "lastSeen": (now - timedelta(seconds=30)).isoformat().replace("+00:00", "Z"),
            }
        },
    }
    (tmp_path / "digest.json").write_text(json.dumps(digest), encoding="utf-8")
    r = _run(tmp_path)
    assert r.returncode == 1, r.stdout + r.stderr
    payload = json.loads(r.stdout.strip().splitlines()[-1])
    assert payload["ok"] is False
    assert any("ear-offline" in f for f in payload["findings"])


def test_fr9144_finding_when_lastseen_stale(tmp_path: Path):
    now = datetime.now(timezone.utc)
    digest = {
        "ts": now.isoformat().replace("+00:00", "Z"),
        "machines": {
            "flamingo": {
                "online": True,
                "status": "I am online",
                "lastSeen": (now - timedelta(seconds=2000)).isoformat().replace("+00:00", "Z"),
            }
        },
    }
    (tmp_path / "digest.json").write_text(json.dumps(digest), encoding="utf-8")
    r = _run(tmp_path)
    assert r.returncode == 1, r.stdout + r.stderr
    payload = json.loads(r.stdout.strip().splitlines()[-1])
    assert any("lastSeen stale" in f for f in payload["findings"])


def test_fr9144_ok_when_fresh_online(tmp_path: Path):
    now = datetime.now(timezone.utc)
    digest = {
        "ts": now.isoformat().replace("+00:00", "Z"),
        "machines": {
            "marchhare": {
                "online": True,
                "status": "I am online",
                "lastSeen": (now - timedelta(seconds=10)).isoformat().replace("+00:00", "Z"),
            }
        },
    }
    (tmp_path / "digest.json").write_text(json.dumps(digest), encoding="utf-8")
    r = _run(tmp_path)
    # Local ircBob may be Running/Stopped on this seat; only assert digest findings empty
    # when service is Running or skipped/missing.
    payload = json.loads(r.stdout.strip().splitlines()[-1])
    digest_findings = [f for f in payload["findings"] if not f.startswith("local ircBob")]
    assert digest_findings == [], payload


def test_fr9144_validateset_includes_ircbob_ear():
    text = INVOKE.read_text(encoding="utf-8")
    assert "ircbob_ear" in text
    assert "'ircbob_ear'" in text


def test_fr9144_monitor_py_shipped():
    assert MONITOR.is_file()
