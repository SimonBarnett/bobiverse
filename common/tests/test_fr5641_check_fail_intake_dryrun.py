"""FR #5641: Write-CheckFailIntake must honor -DryRun (and ReleaseJson test hooks).

pytest DryRun + foreign evil.example URLs logged asset-url-rejected but still filed
real intake twins (#5639) because Send-BobiverseUpdateFailureIntake was called without -DryRun.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest
from repo_layout import ROOT

UPD = ROOT / "common/scripts/Update-BobiverseService.ps1"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md"
PS = shutil.which("powershell.exe") or shutil.which("powershell")
win = pytest.mark.skipif(os.name != "nt" or not PS, reason="needs Windows PowerShell")


def _write_check_fn(text: str) -> str:
    return text[
        text.index("function Write-CheckFailIntake") : text.index(
            "function Ensure-ServiceRunning"
        )
    ]


def _set_failure_fn(text: str) -> str:
    return text[
        text.index("function Set-Failure") : text.index("function Write-CheckFailIntake")
    ]


def test_fr5641_write_check_fail_intake_forwards_dryrun():
    t = UPD.read_text(encoding="utf-8")
    assert not UPD.read_bytes().startswith(b"\xef\xbb\xbf")
    fn = _write_check_fn(t)
    assert "FR #5641" in fn
    assert "Send-BobiverseUpdateFailureIntake" in fn
    # Must pass DryRun through (script -DryRun and/or ReleaseJson test hooks).
    assert "-DryRun:$intakeDry" in fn
    assert "ReleaseJson" in fn
    assert "$DryRun" in fn


def test_fr5641_set_failure_forwards_dryrun():
    t = UPD.read_text(encoding="utf-8")
    fn = _set_failure_fn(t)
    assert "FR #5641" in fn
    assert "Send-BobiverseUpdateFailureIntake" in fn
    assert "-DryRun:$intakeDry" in fn


def test_fr5641_docs_name_dryrun_intake():
    skill = SKILL.read_text(encoding="utf-8")
    assert not SKILL.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "5641" in skill
    assert "DryRun" in skill or "dry-run" in skill.lower()


@win
def test_fr5641_dryrun_foreign_url_intake_is_dryrun_only(tmp_path):
    """Live Check -DryRun + evil.example must log reject and only DRYRUN intake."""
    root = tmp_path / "airc"
    root.mkdir()
    (root / "VERSION").write_text("0.1.16\n")
    state = tmp_path / "state"
    state.mkdir()
    rel = {
        "tag_name": "v0.1.17",
        "assets": [
            {
                "name": "airc-0.1.17.msi",
                "browser_download_url": "https://evil.example/x/airc-0.1.17.msi",
            },
            {
                "name": "airc-0.1.17.msi.sha256",
                "browser_download_url": "https://evil.example/x/airc-0.1.17.msi.sha256",
            },
        ],
    }
    rj = tmp_path / "release.json"
    rj.write_text(json.dumps(rel))
    args = [
        PS,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(UPD),
        "-Product",
        "airc",
        "-InstallRoot",
        str(root),
        "-StateDir",
        str(state),
        "-Mode",
        "Check",
        "-DryRun",
        "-ReleaseJson",
        str(rj),
        "-ForceCheck",
    ]
    p = subprocess.run(args, capture_output=True, text=True, timeout=120)
    log = (state / "update.log").read_text() if (state / "update.log").exists() else ""
    out = (p.stdout or "") + (p.stderr or "")
    assert p.returncode == 0
    assert "asset-url-rejected" in log
    assert "would-update" not in log
    assert "DRYRUN" in out
    assert "Report-BobiverseIntakeIssue" in out
