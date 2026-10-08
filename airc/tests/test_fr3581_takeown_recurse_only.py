"""FR #3581: LogsOnly Protect must not takeown /R the whole ProgramData tree."""
from __future__ import annotations

import os
import subprocess
import textwrap
import time
from pathlib import Path

import pytest

from repo_layout import ROOT

COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"


def _ps(script: str, env: dict | None = None, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    e = os.environ.copy()
    if env:
        e.update(env)
    return subprocess.run(
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
        timeout=timeout,
        cwd=str(ROOT),
        env=e,
    )


def test_fr3581_source_takeown_r_gated_on_recurse_and_setowner():
    t = COMMON.read_text(encoding="utf-8-sig")
    assert "FR #3581" in t
    assert "SetOwner" in t
    # /R must be gated on -Recurse, not merely PSIsContainer.
    assert "$Recurse -and $item.PSIsContainer" in t or (
        "$Recurse" in t and "/R /D Y" in t and "PSIsContainer" in t
    )
    # Must not use the old container-only /R gate as the sole condition.
    bad = 'if ($item.PSIsContainer) {\r\n                    $tc = \'takeown /F "\' + $item.FullName + \'" /A /R /D Y'
    bad2 = 'if ($item.PSIsContainer) {\n                    $tc = \'takeown /F "\' + $item.FullName + \'" /A /R /D Y'
    assert bad not in t and bad2 not in t
    skill = SKILL.read_text(encoding="utf-8")
    assert "3581" in skill


@pytest.mark.skipif(os.name != "nt", reason="Windows only")
def test_fr3581_logs_only_does_not_touch_update_tree(tmp_path: Path):
    """LogsOnly must not takeown /R update\\ (owners stay; finishes fast).

    Root Set-Acl may refresh inherited ACEs on children (CI|OI); that is fine and
    instant. The #3581 defect was takeown /R walking every update\\ file and
    changing owners (917s on 30k files). Pin owner + readability + time budget.
    """
    pd = tmp_path / "ProgramDataBobiverse"
    update = pd / "update" / "airc" / "pad"
    update.mkdir(parents=True)
    # Enough files that /R would be slow and observable; keep N modest for CI.
    n = 200
    for i in range(n):
        (update / f"blob-{i}.bin").write_bytes(b"x" * 64)
    probe = update / "blob-0.bin"

    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        $script:BobiverseProgramDataProtectCache = @{{}}
        $env:BOBIVERSE_PROGRAMDATA_ROOT = '{pd}'
        $probe = '{probe}'
        $before = Get-Acl -LiteralPath $probe
        $ownerBefore = $before.Owner
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $null = Ensure-BobiverseProgramDataRoot -Root '{pd}' -ProtectMode LogsOnly *>&1
        $sw.Stop()
        $after = Get-Acl -LiteralPath $probe
        if ($after.Owner -ne $ownerBefore) {{
          throw ("update file owner changed: " + $ownerBefore + " -> " + $after.Owner)
        }}
        # Must still be able to read the update blob (no empty-DACL orphan).
        $bytes = [IO.File]::ReadAllBytes($probe)
        if ($bytes.Length -lt 1) {{ throw 'update probe unreadable or empty' }}
        # Soft budget: LogsOnly must not walk thousands of update files via takeown /R.
        if ($sw.ElapsedMilliseconds -gt 15000) {{
          throw ("LogsOnly too slow ms=" + $sw.ElapsedMilliseconds)
        }}
        Write-Output ("ok ms=" + $sw.ElapsedMilliseconds)
        """
    )
    t0 = time.time()
    proc = _ps(
        script,
        env={"BOBIVERSE_PROGRAMDATA_ROOT": str(pd)},
        timeout=60,
    )
    wall = time.time() - t0
    assert proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")
    assert "ok ms=" in (proc.stdout or "")
    assert wall < 30.0
