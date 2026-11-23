# -*- coding: utf-8 -*-
"""FR #9187: tray hotpatch stage/install must refuse dollar-stripped Invoke-BobFleet.ps1."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from repo_layout import ROOT

BOB = ROOT / "bob"
if not (BOB / "scripts" / "Stage-BobTrayHotpatchArtifact.ps1").is_file():
    BOB = ROOT
STAGE = BOB / "scripts" / "Stage-BobTrayHotpatchArtifact.ps1"
INSTALL = BOB / "scripts" / "Install-BobTrayHotpatch.ps1"
COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
FLEET = BOB / "tray" / "src" / "Private" / "Invoke-BobFleet.ps1"
WF = ROOT / ".github" / "workflows" / "build-bob-tray.yml"
PS = shutil.which("powershell.exe") or shutil.which("powershell")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")


def _txt(p: Path) -> str:
    assert p.is_file(), p
    return p.read_text(encoding="utf-8-sig")


def test_fr9187_stage_and_install_call_fleet_parse_gate():
    stage = _txt(STAGE)
    install = _txt(INSTALL)
    assert "FR #9187" in stage or "Assert-BobiverseInvokeBobFleetParses" in stage
    assert "FR #9187" in install or "Assert-BobiverseInvokeBobFleetParses" in install
    assert "Assert-BobiverseInvokeBobFleetParses" in stage
    assert "Assert-BobiverseInvokeBobFleetParses" in install
    # Official hotpatch must refuse nameless param([string]) before promote.
    assert "param([string])" in stage or "fleet parse" in stage.lower() or "9187" in stage


def test_fr9187_build_workflow_gates_staged_fleet():
    w = _txt(WF)
    assert "Assert-BobiverseInvokeBobFleetParses" in w or "Invoke-BobFleet" in w
    assert "9187" in w or "fleet" in w.lower()


def test_fr9187_repo_fleet_still_keeps_dollar_names():
    text = _txt(FLEET)
    assert "param([string]$Body)" in text
    assert "param([string])" not in text
    assert "return $false" in text


@needs_ps
def test_fr9187_stage_refuses_stripped_fleet(tmp_path: Path):
    """Stage copies tray src then must fail if Invoke-BobFleet is nameless."""
    assert STAGE.is_file() and COMMON.is_file() and FLEET.is_file()
    # Mini repo: bob/tray with stripped fleet only under src/Private + minimal Public/tools.
    mini = tmp_path / "repo"
    tray = mini / "bob" / "tray"
    priv = tray / "src" / "Private"
    pub = tray / "src" / "Public"
    tools = tray / "tools"
    for d in (priv, pub, tools):
        d.mkdir(parents=True)
    stripped = (
        "function Test-BobFrBodyDispatched {\n"
        "    param([string])\n"
        "    return False\n"
        "}\n"
    )
    (priv / "Invoke-BobFleet.ps1").write_text(stripped, encoding="utf-8")
    (pub / "Get-BobTrayHover.ps1").write_text("function Get-BobTrayHover { }\n", encoding="utf-8")
    (tools / "Watch-BobTray.ps1").write_text("# watch\n", encoding="utf-8")
    # BobBridge stubs so Stage can copy src tree.
    (tray / "src" / "BobBridge.psd1").write_text("@{ ModuleVersion = '0.0' }\n", encoding="utf-8")
    (tray / "src" / "BobBridge.psm1").write_text("# stub\n", encoding="utf-8")
    stage_dir = tmp_path / "stage"
    # Dot Common then run Stage (Stage dots Common itself after our change).
    script = tmp_path / "run.ps1"
    body = rf"""
$ErrorActionPreference = 'Stop'
$common = '{COMMON}'
. $common
try {{
  & '{STAGE}' -RepoRoot '{mini}' -StageDir '{stage_dir}' -Commit 'deadbeef'
  Write-Output 'UNEXPECTED_OK'
  exit 0
}} catch {{
  Write-Output ('FAIL=' + $_.Exception.Message)
  if ($_.Exception.Message -notmatch '9187|9035|nameless|parse|fleet') {{ exit 2 }}
  exit 1
}}
"""
    script.write_text(body, encoding="utf-8")
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=120,
        encoding="utf-8",
        errors="replace",
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert "UNEXPECTED_OK" not in out, out
    assert r.returncode != 0, out
    assert "FAIL=" in out, out
