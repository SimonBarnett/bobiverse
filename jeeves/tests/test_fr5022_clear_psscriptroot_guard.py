"""FR #5022: Clear-BobiverseJobWorktrees prelude must tolerate empty $PSScriptRoot."""
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


def test_fr5022_script_guards_psscriptroot_before_join_path():
    t = SCRIPT.read_text(encoding="utf-8")
    assert "FR #5022" in t
    # Guard must wrap Join-Path so Invoke-Expression prelude does not throw.
    assert "if ($PSScriptRoot)" in t
    idx_guard = t.find("if ($PSScriptRoot)")
    idx_join = t.find("Join-Path $PSScriptRoot 'Bobiverse-Common.ps1'")
    assert idx_guard > 0 and idx_join > idx_guard


@WIN
def test_fr5022_load_functions_prelude_with_empty_psscriptroot():
    """Reproduce the 1.0.4 build regression: split prelude + Invoke-Expression."""
    body = (
        "if (-not (Get-Command Test-IsJobWorktreePath -ErrorAction SilentlyContinue)) "
        "{ throw 'missing Test-IsJobWorktreePath' }; "
        "Write-Output 'prelude_ok'"
    )
    cmd = (
        "$ErrorActionPreference='Stop'; "
        f"$raw = Get-Content -LiteralPath '{SCRIPT}' -Raw; "
        "$fn = ($raw -split '(?m)^if \\(-not \\$RepoRoot\\)')[0]; "
        "Invoke-Expression $fn; "
        + body
    )
    r = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            cmd,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "prelude_ok" in (r.stdout or "")


def test_fr5022_temp_product_orphan_excludes_ref_leaves():
    t = SCRIPT.read_text(encoding="utf-8")
    assert "a-search-ref-4003" in t  # comment cites the build-ref leaf
    assert "-notmatch '(?i)-ref-\\d'" in t

