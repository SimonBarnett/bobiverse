"""FR #3698: Clear foreign live-pid markers + bobiverse-named leafs + drive-mismatch WARN."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "common" / "scripts" / "Clear-BobiverseJobWorktrees.ps1"
FLEET = REPO / "common" / ".grok" / "skills" / "bobiverse-fleet-ops" / "SKILL.md"
FR_SKILL = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"

WIN = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("powershell"),
    reason="needs Windows PowerShell",
)


def _load_functions_ps(script: Path, body: str) -> str:
    """Dot the Clear script's function block (before RepoRoot bootstrap), then run body."""
    return (
        "$ErrorActionPreference='Stop'; "
        f"$raw = Get-Content -LiteralPath '{script}' -Raw; "
        "$fn = ($raw -split '(?m)^if \\(-not \\$RepoRoot\\)')[0]; "
        "Invoke-Expression $fn; "
        + body
    )


def test_fr3698_script_pins():
    t = SCRIPT.read_text(encoding="utf-8")
    assert "FR #3698" in t
    assert "StaleSeatHours" in t
    assert "FullReclaim" in t
    assert "CommandLine" in t
    assert "other volume" in t.lower() or "RepoRoot drive" in t
    assert "WARN FR #3698" in t or "WARN" in t and "3698" in t


def test_fr3698_leaf_block_covers_bobiverse_named():
    t = SCRIPT.read_text(encoding="utf-8")
    block = t[t.find("function Test-IsJobWorktreePath") : t.find("function Test-WorktreeProtected")]
    assert "bobiverse" in block.lower() or "[a-z0-9_.]+" in block


@WIN
def test_fr3698_foreign_live_pid_not_protected_on_full_reclaim(tmp_path: Path):
    tree = tmp_path / "job-fr-bobiverse-3698"
    tree.mkdir()
    # Explorer is live and will not cite this temp tree. Age marker past StaleSeatHours
    # so only a (wrong) live-pid short-circuit could still protect — it must not.
    body = (
        f"$p = '{tree}'; "
        "$foreign = @(Get-Process -Name explorer -ErrorAction SilentlyContinue | Select-Object -First 1); "
        "if (-not $foreign.Count) { Write-Output 'SKIP no-explorer'; exit 0 }; "
        "$fp = [int]$foreign[0].Id; "
        "$marker = Join-Path $p '.bobiverse-seat'; "
        "$json = ('{{\"nick\":\"other\",\"pid\":' + $fp + ',\"issue\":1,\"repo\":\"SimonBarnett/bobiverse\"}}'); "
        "Set-Content -LiteralPath $marker -Value $json -Encoding utf8; "
        "(Get-Item -LiteralPath $marker).LastWriteTimeUtc = [datetime]::UtcNow.AddHours(-72); "
        "$script:ClearStaleSeatHours = 48; "
        "$full = [bool](Test-WorktreeProtected -Path $p -FullReclaim:$true); "
        "if ($full) { Write-Output ('FAIL full-protected pid=' + $fp); exit 1 }; "
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
    out = r.stdout or ""
    assert "ok" in out or "SKIP" in out


@WIN
def test_fr3698_fresh_marker_soft_cap_protects_dead_or_foreign(tmp_path: Path):
    tree = tmp_path / "job-fr-9999"
    tree.mkdir()
    (tree / ".bobiverse-seat").write_text(
        '{"nick":"mid-fr","pid":2147483000,"issue":9999,"repo":"SimonBarnett/bobiverse"}',
        encoding="utf-8",
    )
    body = (
        f"$p = '{tree}'; "
        "$soft = [bool](Test-WorktreeProtected -Path $p -FullReclaim:$false); "
        "if (-not $soft) { Write-Output 'FAIL soft-unprotected'; exit 1 }; "
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


@WIN
def test_fr3698_leaf_matcher_accepts_bobiverse_named(tmp_path: Path):
    root = tmp_path / "repo-root"
    root.mkdir()
    leaves = [
        "job-fr-bobiverse-3687",
        "job-mrb-bobiverse-3693",
        "fr-bobiverse-3181",
        "docs-mrb-3433",
        "job-fr-3400",
        "tmp-main-fr3391-check",
        "job-fr-3641-unmarked",
        "job-fr-3641-stale",
    ]
    for leaf in leaves:
        (root / leaf).mkdir()
    listed = ",".join(leaves)
    body = (
        f"$root = '{root}'; "
        f"$cases = @({','.join(repr(x) for x in leaves)}); "
        "$bad = @(); "
        "foreach ($leaf in $cases) { "
        "  $p = Join-Path $root $leaf; "
        "  if (-not (Test-IsJobWorktreePath -Path $p -RootFull $root -KeepFull '')) { $bad += $leaf } "
        "}; "
        "if ($bad.Count) { Write-Output ('FAIL ' + ($bad -join ',')); exit 1 }; "
        "Write-Output 'ok'"
    )
    # Use PS array literals instead of Python repr
    ps_cases = "@('" + "','".join(leaves) + "')"
    body = (
        f"$root = '{root}'; "
        f"$cases = {ps_cases}; "
        "$bad = @(); "
        "foreach ($leaf in $cases) { "
        "  $p = Join-Path $root $leaf; "
        "  if (-not (Test-IsJobWorktreePath -Path $p -RootFull $root -KeepFull '')) { $bad += $leaf } "
        "}; "
        "if ($bad.Count) { Write-Output ('FAIL ' + ($bad -join ',')); exit 1 }; "
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
    del listed


def test_fr3698_docs_skill_mention():
    fleet = FLEET.read_text(encoding="utf-8")
    assert "3698" in fleet
    fr = FR_SKILL.read_text(encoding="utf-8")
    assert "Clear-BobiverseJobWorktrees" in fr
