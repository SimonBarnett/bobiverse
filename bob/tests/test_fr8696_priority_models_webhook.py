"""FR #8696 / BOB-51: Priority dry-run cites models webhook Priority row."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from repo_layout import ROOT

FIXTURE = ROOT / "bob" / "tests" / "fixtures" / "models-webhook-priority.json"
PRIV = ROOT / "bob" / "tray" / "src" / "Private" / "Get-BobModelsWebhook.ps1"
PUB = ROOT / "bob" / "tray" / "src" / "Public" / "Invoke-BobPriorityModelsDryRun.ps1"
EVIDENCE = ROOT / "bob" / "docs" / "bob-51-priority-models-webhook-evidence.md"


def test_evidence_doc_exists():
    text = EVIDENCE.read_text(encoding="utf-8")
    assert "BOB-51" in text
    assert "priority-models-dry-run.log" in text
    assert "models webhook" in text.lower()


def test_fixture_has_priority_row():
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    ids = [str(a.get("id") or "").lower() for a in doc["agents"]]
    assert "priority" in ids


def test_priority_dry_run_cites_webhook(tmp_path: Path):
    log_path = tmp_path / "priority-models-dry-run.log"
    ps = f"""
$ErrorActionPreference = 'Stop'
. '{PRIV.as_posix()}'
. '{PUB.as_posix()}'
$r = Invoke-BobPriorityModelsDryRun -FixturePath '{FIXTURE.as_posix()}' -LogPath '{log_path.as_posix()}' -Uri 'https://bob.ntsa.uk/bob/v1/models' -Quiet
if ($r.Agent -ne 'priority') {{ throw 'agent' }}
if ($r.Model -ne 'grok-4.6') {{ throw 'model' }}
if ($r.Context -ne '256') {{ throw 'context' }}
if ($r.Effort -ne 'high') {{ throw 'effort' }}
if ($r.Webhook -notmatch 'bob/v1/models') {{ throw 'webhook' }}
"""
    script = tmp_path / "run.ps1"
    script.write_text(ps, encoding="utf-8")
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    body = log_path.read_text(encoding="utf-8")
    assert "agent=priority" in body
    assert "webhook=https://bob.ntsa.uk/bob/v1/models" in body
    assert "model=grok-4.6" in body
    assert "context=256" in body
    assert "effort=high" in body
    assert "source=models-webhook-priority-row" in body
    assert "launch=dry-run" in body


def test_missing_priority_row_fails(tmp_path: Path):
    bad = tmp_path / "no-priority.json"
    bad.write_text(json.dumps({"agents": [{"id": "plan", "model": "x"}]}), encoding="utf-8")
    log_path = tmp_path / "out.log"
    ps = f"""
$ErrorActionPreference = 'Stop'
. '{PRIV.as_posix()}'
. '{PUB.as_posix()}'
try {{
  Invoke-BobPriorityModelsDryRun -FixturePath '{bad.as_posix()}' -LogPath '{log_path.as_posix()}' -Quiet | Out-Null
  exit 2
}} catch {{
  if ($_.Exception.Message -notmatch 'no Priority row') {{ throw }}
  exit 0
}}
"""
    script = tmp_path / "run-bad.ps1"
    script.write_text(ps, encoding="utf-8")
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr