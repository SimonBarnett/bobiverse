# -*- coding: utf-8 -*-
"""FR #9354: Pack vendors PlanAgent.exe from skills-visionary (sha256 + MANIFEST)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from repo_layout import ROOT

PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
HELPERS = ROOT / "common" / "scripts" / "Bobiverse-FetchHelpers.ps1"
EVIDENCE = ROOT / "bob" / "docs" / "bob-49-bob-ear-msi-include-plan-evidence.md"
FIXTURE = ROOT / "bob" / "tests" / "fixtures" / "PlanAgent.exe"


def test_fr9354_helpers_and_pack_pins():
    helpers = HELPERS.read_text(encoding="utf-8-sig")
    assert "Save-BobiverseGhReleaseVerifiedExe" in helpers
    assert "Read-BobiverseSha256SumFile" in helpers
    assert "Write-BobiverseVendoredExeManifest" in helpers
    pack = PACK.read_text(encoding="utf-8-sig")
    assert "SkipPlanAgentExe" in pack
    assert "SimonBarnett/skills-visionary" in pack
    assert "PlanAgent.exe" in pack
    assert "PlanAgent.MANIFEST.json" in pack
    assert "fr_vendor=9354" in pack
    assert "Save-BobiverseGhReleaseVerifiedExe" in pack
    # Priority aligned to release download as well.
    assert "SimonBarnett/priority-mcp" in pack
    assert "PriorityAgent.MANIFEST.json" in pack
    assert FIXTURE.is_file()
    assert FIXTURE.read_bytes()[:2] == b"MZ"


def test_fr9354_evidence_doc_mentions_vendor():
    text = EVIDENCE.read_text(encoding="utf-8")
    assert "9354" in text or "PlanAgent" in text
    assert "skills-visionary" in text.lower() or "PlanAgent" in text


def test_fr9354_sha256_sum_file_parse(tmp_path: Path):
    """Offline: Read-BobiverseSha256SumFile accepts hex + filename sidecars."""
    side = tmp_path / "PlanAgent.exe.sha256"
    side.write_text(
        "64865206e4a6932a6b8b5f2fc38b259aae986452c6e1b2461a64c22b0b13c472  PlanAgent.exe\n",
        encoding="ascii",
    )
    ps = f"""
$ErrorActionPreference = 'Stop'
. '{HELPERS}'
$h = Read-BobiverseSha256SumFile -Path '{side}'
if ($h -ne '64865206e4a6932a6b8b5f2fc38b259aae986452c6e1b2461a64c22b0b13c472') {{ throw "got=$h" }}
Write-Output 'ok'
"""
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ok" in (r.stdout or "")


def test_fr9354_vendored_manifest_writer(tmp_path: Path):
    helpers = HELPERS
    man = tmp_path / "PlanAgent.MANIFEST.json"
    ps = f"""
$ErrorActionPreference = 'Stop'
. '{helpers}'
$info = @{{
  tag = 'plan-v1.0.5'
  sha256 = 'abc'
  bytes = 12
  repo = 'SimonBarnett/skills-visionary'
  asset = 'PlanAgent.exe'
  url = 'https://example.test/PlanAgent.exe'
  path = 'plan\\PlanAgent.exe'
}}
Write-BobiverseVendoredExeManifest -Path '{man}' -Info $info -Fr '9354' -Bob 'BOB-49' | Out-Null
Write-Output 'ok'
"""
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    doc = json.loads(man.read_text(encoding="utf-8"))
    assert doc["fr"] == "9354"
    assert doc["bob"] == "BOB-49"
    assert doc["tag"] == "plan-v1.0.5"
    assert doc["repo"] == "SimonBarnett/skills-visionary"
    assert doc["asset"] == "PlanAgent.exe"
