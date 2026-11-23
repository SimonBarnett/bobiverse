"""FR #9104: github_rate_limit monitor EXIT1 below floor; dry-run ok."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import REPO

MONITOR = REPO / "jeeves" / "tools" / "monitor" / "github_rate_limit.py"


def _run(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    if env:
        e.update(env)
    return subprocess.run(
        [sys.executable, str(MONITOR), *args],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(MONITOR.parent),
        env=e,
    )


def test_fr9104_dry_run_ok():
    r = _run("--dry-run")
    assert r.returncode == 0, r.stderr
    doc = json.loads(r.stdout.strip())
    assert doc.get("ok") is True
    assert doc.get("dry_run") is True
    assert doc.get("check") == "github_rate_limit"


def test_fr9104_remaining_below_floor_exit1(monkeypatch):
    r = _run(
        "--remaining",
        "100",
        "--floor",
        "500",
        "--limit",
        "5000",
        env={"BOB_MACHINE_ID": "flamingo"},
    )
    assert r.returncode == 1, (r.stdout, r.stderr)
    doc = json.loads(r.stdout.strip())
    assert doc.get("ok") is False
    assert doc.get("remaining") == 100
    assert doc.get("floor") == 500
    assert doc.get("machine") == "flamingo"
    assert any("core.remaining=100" in f for f in doc.get("findings") or [])


def test_fr9104_remaining_at_or_above_floor_ok():
    r = _run(
        "--remaining",
        "500",
        "--floor",
        "500",
        env={"BOB_MACHINE_ID": "marchhare"},
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    doc = json.loads(r.stdout.strip())
    assert doc.get("ok") is True
    assert doc.get("findings") == []
    assert doc.get("machine") == "marchhare"


def test_fr9104_env_remaining_override():
    r = _run(
        "--floor",
        "200",
        env={
            "BOB_MACHINE_ID": "rq",
            "BOB_GITHUB_RATE_REMAINING": "50",
            "BOB_GITHUB_RATE_LIMIT": "5000",
        },
    )
    assert r.returncode == 1, (r.stdout, r.stderr)
    doc = json.loads(r.stdout.strip())
    assert doc.get("remaining") == 50
    assert doc.get("source") == "env"
