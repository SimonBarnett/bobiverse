"""FR #3717: Clear pre-rmdirs cdk.out* before git worktree remove (Filename too long)."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "common" / "scripts" / "Clear-BobiverseJobWorktrees.ps1"
FR_SKILL = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"
FLEET = REPO / "common" / ".grok" / "skills" / "bobiverse-fleet-ops" / "SKILL.md"

WIN = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("powershell"),
    reason="needs Windows PowerShell",
)


def test_fr3717_clear_script_pins_cdkout_rmdir():
    t = SCRIPT.read_text(encoding="utf-8")
    assert "FR #3717" in t
    assert "cdk.out" in t
    assert "rmdir /s /q" in t
    assert "Filename too long" in t or "Filename too long" in t.lower() or "MAX_PATH" in t
    # Prefer cmd rmdir for leftovers (Remove-Item also fails on deep asset trees).
    assert "cmd.exe /c" in t or "cmd /c" in t
    raw = SCRIPT.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert all(b < 128 for b in raw), "Clear.ps1 must stay BOM-less ASCII (fr3391)"


def test_fr3717_docs_skill_mention():
    fr = FR_SKILL.read_text(encoding="utf-8")
    fleet = FLEET.read_text(encoding="utf-8")
    assert "3717" in fr or "cdk.out" in fr
    assert "3717" in fleet or "cdk.out" in fleet


@WIN
def test_fr3717_pre_rmdir_removes_cdkout_before_git(tmp_path: Path):
    """Helper path: cdk.out* under a fake job tree is removed via cmd rmdir."""
    # Dot the Clear script's function block (before RepoRoot bootstrap), then call helper.
    tree = tmp_path / "job-fr-a-search-3717"
    deep = tree / "cdk.out-fr136" / ("a" * 40) / ("b" * 40)
    deep.mkdir(parents=True)
    (deep / "asset.txt").write_text("x\n", encoding="utf-8")
    assert (tree / "cdk.out-fr136").is_dir()

    ps = (
        "$ErrorActionPreference='Stop'; "
        f"$raw = Get-Content -LiteralPath '{SCRIPT}' -Raw; "
        "$fn = ($raw -split '(?m)^if \\(-not \\$RepoRoot\\)')[0]; "
        "Invoke-Expression $fn; "
        f"Remove-BobiverseDeepWorktreeDirs -WorktreePath '{tree}'; "
        f"if (Test-Path -LiteralPath '{tree / 'cdk.out-fr136'}') {{ throw 'cdk.out still present' }}; "
        "Write-Output 'cdkout-gone'"
    )
    r = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            ps,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    out = (r.stdout or "") + "\n" + (r.stderr or "")
    assert r.returncode == 0, out
    assert "cdkout-gone" in out
    assert not (tree / "cdk.out-fr136").exists()
