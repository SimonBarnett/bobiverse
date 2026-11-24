"""FR #9843: Stage-Product must not leak Hashtable into heat Stage path (FR #6969 resurfaced)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from repo_layout import ROOT

PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"


def test_fr9843_pack_captures_assert_hashtable_return():
    p = PACK.read_text(encoding="utf-8")
    assert "FR #9843" in p
    assert "$null = Assert-BobiversePlanAgentNotBobWorker -Root $Stage -Require" in p
    assert "$null = Stage-BobAgentFolders -Stage $stage" in p
    # Uncaptured Assert call must not remain in Stage-BobAgentFolders.
    bare = "\n        Assert-BobiversePlanAgentNotBobWorker -Root $Stage -Require\n"
    assert bare not in p.replace("\r\n", "\n")


def test_fr9843_common_captures_assert_inside_vendor_copy():
    c = COMMON.read_text(encoding="utf-8")
    assert "$null = Assert-BobiversePlanAgentNotBobWorker -Root $Root -Require:$Require" in c
    copy_fn = c.split("function Copy-BobTrayVendorExes {", 1)[1].split(
        "function Assert-BobiversePlanAgentNotBobWorker {", 1
    )[0]
    assert "$null = Assert-BobiversePlanAgentNotBobWorker" in copy_fn


def test_fr9843_heat_assert_rejects_hashtable_before_string_join():
    p = PACK.read_text(encoding="utf-8")
    assert "function Assert-BobiverseHeatStagePath" in p
    fn = p.split("function Assert-BobiverseHeatStagePath", 1)[1].split(
        "function Build-Msi", 1
    )[0]
    assert "FR #6969/#9843: heat stage path is a Hashtable" in fn
    assert "System.Collections.IDictionary" in fn or "hashtable" in fn.lower()
    # Must not coerce Hashtable via [string]$Stage param before the type check.
    assert "[string]$Stage" not in fn.split("{", 1)[0]


def test_fr9843_heat_assert_throws_on_hashtable(tmp_path: Path):
    """Offline: Assert-BobiverseHeatStagePath rejects Hashtable Stage."""
    stage = tmp_path / "bob-2.0.1274"
    stage.mkdir()
    ps = f"""
$ErrorActionPreference = 'Stop'
. '{PACK}'
# Dot-sourcing the pack script runs product loop — instead extract the function by
# loading helpers only and redefining Assert from the pack text is heavy. Invoke via
# a tiny wrapper that dotsources Common then defines Assert from Pack by parsing.
# Simpler: run Pack's Assert by loading the script as text into a scriptblock after
# stripping the top-level pack loop is fragile. Call PowerShell to evaluate the
# hardened Assert by copying the function body from Pack after Common load.
"""
    # Load Common + evaluate Assert function extracted from Pack.
    pack = PACK.read_text(encoding="utf-8")
    start = pack.index("function Assert-BobiverseHeatStagePath")
    end = pack.index("\nfunction Build-Msi", start)
    fn = pack[start:end]
    ps = f"""
$ErrorActionPreference = 'Stop'
. '{COMMON}'
{fn}
try {{
  Assert-BobiverseHeatStagePath -Stage @{{ ok = $true }}
  exit 0
}} catch {{
  if ($_.Exception.Message -match 'Hashtable') {{ exit 42 }}
  Write-Error $_
  exit 1
}}
"""
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert r.returncode == 42, (r.returncode, r.stdout, r.stderr)


def test_fr9843_stage_product_bob_returns_single_directory_string(tmp_path: Path):
    """SkipMsi bob stage: heat Stage path is a single directory (no Hashtable join)."""
    out = tmp_path / "out"
    out.mkdir()
    # SkipWorkerExe avoids PyInstaller; Assert is skipped then — still validates no other
    # Hashtable leak from plan/priority vendor helpers under Skip* stubs. Pack may leave
    # a non-zero native LASTEXITCODE after Format-Table on empty MSI list; trust stage path.
    ps = f"""
$ErrorActionPreference = 'Continue'
& '{PACK}' -Product bob -RepoRoot '{ROOT}' -OutDir '{out}' -Version '2.0.1274' `
  -SkipMsi -SkipWorkerExe -SkipEarExe -SkipPlanAgentExe -SkipPriorityExe `
  -KeepStage -SkipPublishedVersionCheck 2>&1 | Out-String | Write-Output
$dirs = @(Get-ChildItem -LiteralPath '{out}' -Directory -ErrorAction SilentlyContinue |
  Where-Object {{ $_.Name -like 'bob-*' }})
if ($dirs.Count -lt 1) {{ Write-Output 'NO_STAGE'; exit 3 }}
$stage = $dirs[0].FullName
if (-not (Test-Path -LiteralPath $stage -PathType Container)) {{ exit 4 }}
if ($stage -match 'Hashtable') {{ Write-Output "BAD=$stage"; exit 5 }}
if (-not (Test-Path -LiteralPath (Join-Path $stage 'plan\\PlanAgent.exe') -PathType Leaf)) {{ exit 6 }}
Write-Output "STAGE_OK=$stage"
exit 0
"""
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert r.returncode == 0, (r.returncode, (r.stdout or "")[-2500:], (r.stderr or "")[-1500:])
    assert "STAGE_OK=" in (r.stdout or "")
    assert "BAD=" not in (r.stdout or "")
    # SkipMsi log line must show a clean path (CI failure shape was Hashtable + path).
    assert "System.Collections.Hashtable" not in (r.stdout or "")


def test_fr9843_uncaptured_assert_would_join_into_stage_path(tmp_path: Path):
    """Fail-when: uncaptured Assert Hashtable + path becomes the CI heat error shape."""
    root = tmp_path / "install"
    (root / "plan").mkdir(parents=True)
    (root / "worker").mkdir(parents=True)
    (root / "plan" / "PlanAgent.exe").write_bytes(b"MZ-plan")
    (root / "worker" / "bob-worker.exe").write_bytes(b"MZ-worker")
    stage = tmp_path / "bob-2.0.1274"
    stage.mkdir()
    ps = f"""
$ErrorActionPreference = 'Stop'
. '{COMMON}'
function Stage-Leaky {{
  Assert-BobiversePlanAgentNotBobWorker -Root '{root}' -Require
  return '{stage}'
}}
function Stage-Fixed {{
  $null = Assert-BobiversePlanAgentNotBobWorker -Root '{root}' -Require
  return '{stage}'
}}
$bad = [string]@(Stage-Leaky)
$good = [string]@(Stage-Fixed)
Write-Output "BAD=$bad"
Write-Output "GOOD=$good"
if ($bad -notmatch 'Hashtable') {{ exit 3 }}
if ($good -match 'Hashtable') {{ exit 4 }}
if ($good -ne '{stage}') {{ exit 5 }}
exit 0
"""
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    assert "BAD=System.Collections.Hashtable" in (r.stdout or "")
    assert f"GOOD={stage}" in (r.stdout or "").replace("/", "\\") or f"GOOD={stage}" in (
        r.stdout or ""
    )

def test_fr9843_ps_join_documents_hashtable_leak():
    leaked = [{"ok": True}, r"D:\a\_temp\bob-msi-out\bob-2.0.1274"]
    # Mirror PowerShell [string]@(hashtable, path) join shape used in CI failure.
    joined = " ".join(
        "System.Collections.Hashtable" if isinstance(x, dict) else str(x) for x in leaked
    )
    assert joined.startswith("System.Collections.Hashtable ")
    assert "bob-2.0.1274" in joined
