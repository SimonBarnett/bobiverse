"""FR #5279: deterministic bobiverse intake on UPDATE / Apply failure classes."""
from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from repo_layout import ROOT

UPDATER = ROOT / "common/scripts/Update-BobiverseService.ps1"
COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
CONSOLE = ROOT / "airc/scripts/airc_console.py"
DOCS = ROOT / "airc/docs/airc-remote-control.md"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md"


def test_fr5279_source_pins_set_failure_and_schedule():
    upd = UPDATER.read_text(encoding="utf-8")
    common = COMMON.read_text(encoding="utf-8")
    con = CONSOLE.read_text(encoding="utf-8")
    assert "Send-BobiverseUpdateFailureIntake" in common
    assert "Send-BobiverseUpdateFailureIntake" in upd
    assert "FR #5279" in upd and "FR #5279" in common
    assert "idempotency_key" in common.lower() or "IdempotencyKey" in common
    assert "report_update_failure_intake" in con
    assert "updater-missing" in con
    docs = DOCS.read_text(encoding="utf-8")
    skill = SKILL.read_text(encoding="utf-8")
    assert "5279" in docs and "5279" in skill


def test_fr5279_failure_classes_documented():
    common = COMMON.read_text(encoding="utf-8")
    for tag in (
        "download-failed",
        "msiexec-timeout",
        "stop-failed",
        "backup-failed",
        "spawn-failed",
        "updater-missing",
        "asset-url-rejected",
        "msiexec-exit",
    ):
        assert tag in common


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell")
def test_fr5279_helper_dryrun_idempotent_and_redacts():
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        $env:BOB_MACHINE_ID = 'testhost'
        $a = Send-BobiverseUpdateFailureIntake -Product airc -Tag 'v1.0.0' -Result 'download-failed' -Detail 'password=FAKEpw99 token=x' -DryRun
        $b = Send-BobiverseUpdateFailureIntake -Product airc -Tag 'v1.0.0' -Result 'download-failed' -Detail 'password=FAKEpw99 token=x' -DryRun
        if (-not $a.idempotency_key) {{ throw 'missing key' }}
        if ($a.idempotency_key -ne $b.idempotency_key) {{ throw 'key drift' }}
        if ($a.idempotency_key -notmatch 'testhost') {{ throw 'machine missing' }}
        if ($a.idempotency_key -notmatch 'download-failed') {{ throw 'result missing' }}
        if ($a.body -match 'FAKEpw99') {{ throw 'secret leaked' }}
        if ($a.body -notmatch 'redacted') {{ throw 'no redact' }}
        if ($a.kind -ne 'issue') {{ throw 'kind' }}
        if ($a.repo -ne 'SimonBarnett/bobiverse') {{ throw 'repo' }}
        Write-Output ('key=' + $a.idempotency_key)
        """
    )
    p = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        cwd=str(ROOT),
    )
    assert p.returncode == 0, p.stdout + p.stderr
    assert "key=" in p.stdout


@pytest.mark.skipif(os.name != "nt", reason="Windows")
def test_fr5279_schedule_updater_missing_reports_intake(monkeypatch):
    import airc_console as ac

    calls: list[dict] = []

    def fake_report(**kwargs):
        r = dict(kwargs)
        r["idempotency_key"] = "|".join(
            ["airc-update-fail", "x", str(kwargs.get("product")), "-", str(kwargs.get("result"))]
        )
        calls.append(r)
        return {"ok": True, "idempotency_key": r["idempotency_key"]}

    monkeypatch.setattr(ac, "report_update_failure_intake", fake_report)
    monkeypatch.setattr(ac, "_find_update_bobiverse_script", lambda *a, **k: None)
    r = ac.schedule_fleet_update("airc", install_root=str(ROOT / "airc"))
    assert r.status == "updater-missing"
    assert len(calls) == 1
    assert calls[0]["result"] == "updater-missing"
    assert calls[0]["product"] == "airc"
    assert "updater-missing" in calls[0]["idempotency_key"]
    ac.schedule_fleet_update("airc", install_root=str(ROOT / "airc"))
    assert calls[0]["idempotency_key"] == calls[1]["idempotency_key"]
