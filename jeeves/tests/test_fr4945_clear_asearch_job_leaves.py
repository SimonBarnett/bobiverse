"""FR #4945: Clear reclaim a-search-* (and product sibling) job worktree leaves."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "common" / "scripts" / "Clear-BobiverseJobWorktrees.ps1"

WIN = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("powershell"),
    reason="needs Windows PowerShell",
)


def _load_functions_ps(script: Path, body: str) -> str:
    return (
        "$ErrorActionPreference='Stop'; "
        f"$raw = Get-Content -LiteralPath '{script}' -Raw; "
        "$fn = ($raw -split '(?m)^if \\(-not \\$RepoRoot\\)')[0]; "
        "Invoke-Expression $fn; "
        + body
    )


def test_fr4945_script_pins():
    t = SCRIPT.read_text(encoding="utf-8")
    assert "FR #4945" in t
    block = t[
        t.find("function Test-IsJobWorktreePath") : t.find("function Test-ProcessCitesPath")
    ]
    assert r"[a-z][a-z0-9_.-]*-(wt-)?" in block
    assert "a-search-*" in t
    assert "orphanFilters" in t


@WIN
def test_fr4945_leaf_matches_asearch_shapes(tmp_path: Path):
    body = (
        f"$parent = '{tmp_path}'; "
        "$rootFull = [System.IO.Path]::GetFullPath((Join-Path $parent 'a-search')); "
        "New-Item -ItemType Directory -Force -Path $rootFull | Out-Null; "
        "$keep = ''; "
        "$ok = @("
        "  'a-search-wt-fr-4827',"
        "  'a-search-fr-1238',"
        "  'a-search-mrb-1810b',"
        "  'a-search-fix-2075',"
        "  'a-search-wt-docs-mrb-4452',"
        "  'bobiverse-wt-mrb-4940',"
        "  'a-search-mrb-2317-miss'"
        "); "
        "$bad = @('wt-bob-main-1', 'wt-airc-build', 'wt-main', 'a-search-ref-4003', 'notes'); "
        "foreach ($leaf in $ok) { "
        "  $p = Join-Path $parent $leaf; "
        "  New-Item -ItemType Directory -Force -Path $p | Out-Null; "
        "  if (-not (Test-IsJobWorktreePath $p $rootFull $keep)) { "
        "    Write-Output ('FAIL miss ' + $leaf); exit 1 "
        "  } "
        "}; "
        "foreach ($leaf in $bad) { "
        "  $p = Join-Path $parent $leaf; "
        "  New-Item -ItemType Directory -Force -Path $p | Out-Null; "
        "  if (Test-IsJobWorktreePath $p $rootFull $keep) { "
        "    Write-Output ('FAIL hit ' + $leaf); exit 1 "
        "  } "
        "}; "
        "if (Test-IsJobWorktreePath $rootFull $rootFull '') { Write-Output 'FAIL root'; exit 1 }; "
        "Write-Output 'ok'"
    )
    r = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            _load_functions_ps(SCRIPT, body),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    assert "ok" in (r.stdout or "")
