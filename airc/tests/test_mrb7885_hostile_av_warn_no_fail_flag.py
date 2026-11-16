# -*- coding: utf-8 -*-
"""MRB #7885: FR #7878 third-party AV warn must not set install-airc-fail-reported.flag."""
from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

from repo_layout import ROOT

AV = ROOT / "common" / "scripts" / "Register-BobiverseAvExclusions.ps1"
COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
INSTALL = ROOT / "airc" / "scripts" / "Install-Airc.ps1"


def test_mrb7885_common_skip_fail_flag_guards_set_content():
    text = COMMON.read_text(encoding="utf-8-sig")
    fn = text[text.find("function Send-BobiverseAircInstallFailureIntake") :]
    fn = fn[: fn.find("\nfunction ", 1)]
    assert "SkipFailReportedFlag" in fn
    assert "if (-not $SkipFailReportedFlag)" in fn
    assert "install-airc-fail-reported.flag" in fn
    assert "install-warn-intake" in fn


def test_mrb7885_register_passes_skip_fail_flag():
    text = AV.read_text(encoding="utf-8-sig")
    warn = text[text.find("# FR #7878: warn before install") :]
    warn = warn[: warn.find("if ($AssertExePath)")]
    assert "SkipFailReportedFlag" in warn
    assert "Send-BobiverseAircInstallFailureIntake" in warn
    assert "InstallRoot" in warn


def test_mrb7885_install_passes_install_root_to_av():
    text = INSTALL.read_text(encoding="utf-8-sig")
    assert "-InstallRoot $InstallRoot" in text or "-InstallRoot', $InstallRoot" in text
    assert "SkipFailReportedFlag" in AV.read_text(encoding="utf-8-sig")


def test_mrb7885_warn_spy_sees_skip_fail_flag(tmp_path: Path):
    """Behavioural: when the failure intake helper is in scope, warn must pass -SkipFailReportedFlag."""
    spy = tmp_path / "spy.json"
    wrapper = tmp_path / "run.ps1"
    wrapper.write_text(
        textwrap.dedent(
            f"""
            $ErrorActionPreference = 'Continue'
            $global:Mrb7885SpyPath = '{spy.as_posix()}'
            # global: so Get-Command inside & Register-*.ps1 sees the spy (child script scope).
            function global:Send-BobiverseAircInstallFailureIntake {{
                param(
                    [string]$Title,
                    [string]$Body,
                    [string]$InstallRoot = '',
                    [string]$ScriptsDir = '',
                    [switch]$SkipFailReportedFlag,
                    [switch]$DryRun
                )
                $obj = [ordered]@{{
                    Title = $Title
                    Skip = [bool]$SkipFailReportedFlag
                    InstallRoot = $InstallRoot
                }}
                ($obj | ConvertTo-Json -Compress) | Set-Content -LiteralPath $global:Mrb7885SpyPath -Encoding utf8
            }}
            & '{AV.as_posix()}' -Paths '{(tmp_path / "airc").as_posix()}' -Processes airc.exe `
                -Product airc -AntivirusProductsJson '{json.dumps(["Avast Antivirus"])}' `
                -InstallRoot '{(tmp_path / "install").as_posix()}'
            if (-not (Test-Path -LiteralPath $global:Mrb7885SpyPath)) {{ throw 'intake spy not written' }}
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    r = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(wrapper),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out
    data = json.loads(spy.read_text(encoding="utf-8-sig"))
    assert data.get("Skip") is True, data
    assert "third-party antivirus" in (data.get("Title") or "")
    assert data.get("InstallRoot"), data


def test_mrb7885_service_error_names_av_when_exe_present(tmp_path: Path):
    exe = tmp_path / "airc" / "airc.exe"
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"MZ")
    r = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(AV),
            "-Paths",
            str(tmp_path / "airc"),
            "-Processes",
            "airc.exe",
            "-Product",
            "airc",
            "-AntivirusProductsJson",
            json.dumps(["Avast Antivirus"]),
            "-AssertExePath",
            str(exe),
            "-AssertServiceError",
            "Cannot start service Airc",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 2, out
    assert "ERROR FR #7878" in out
    assert "Avast Antivirus" in out
    assert "Cannot start service Airc" in out
