"""docs/mrb-3587 hostile pins for FR #3581 / PR #3587 takeown /R gate."""
from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from repo_layout import ROOT

COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"
POST = ROOT / "common/docs/post-install.md"


def _ps(script: str, env: dict | None = None, timeout: int = 90) -> subprocess.CompletedProcess[str]:
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


def test_mrb3587_source_gates_takeown_r_on_recurse_only():
    t = COMMON.read_text(encoding="utf-8-sig")
    assert "FR #3581" in t
    assert "$Recurse -and $item.PSIsContainer" in t
    assert "SetOwner" in t
    # LogsOnly must recurse logs only, not root.
    assert "ProtectMode -eq 'LogsOnly'" in t or "$ProtectMode -eq 'LogsOnly'" in t
    # Contiguous skill phrase from product merge.
    skill = SKILL.read_text(encoding="utf-8")
    assert "takeown /A /R" in skill or "takeown /A /R" in skill.replace("**", "")
    assert "3581" in skill
    assert "LogsOnly must not takeown" in skill or "must not takeown /R" in skill


def test_mrb3587_post_install_cites_3581_logs_only():
    post = POST.read_text(encoding="utf-8")
    assert "FR #3581" in post or "3581" in post
    assert "LogsOnly" in post or "takeown" in post.lower()


@pytest.mark.skipif(os.name != "nt", reason="Windows only")
def test_mrb3587_logs_only_leaves_update_owner_and_stays_fast(tmp_path: Path):
    """Behavioural pin: LogsOnly must not takeown /R update\\ blobs."""
    pd = tmp_path / "ProgramDataBobiverse"
    update = pd / "update" / "airc" / "pad"
    update.mkdir(parents=True)
    for i in range(120):
        (update / f"f-{i}.bin").write_bytes(b"y" * 32)
    probe = update / "f-0.bin"

    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        $script:BobiverseProgramDataProtectCache = @{{}}
        $env:BOBIVERSE_PROGRAMDATA_ROOT = '{pd}'
        $probe = '{probe}'
        $ownerBefore = (Get-Acl -LiteralPath $probe).Owner
        $sw = [Diagnostics.Stopwatch]::StartNew()
        $null = Ensure-BobiverseProgramDataRoot -Root '{pd}' -ProtectMode LogsOnly *>&1
        $sw.Stop()
        $ownerAfter = (Get-Acl -LiteralPath $probe).Owner
        if ($ownerAfter -ne $ownerBefore) {{
          throw ("owner changed " + $ownerBefore + " -> " + $ownerAfter)
        }}
        [void][IO.File]::ReadAllBytes($probe)
        if ($sw.ElapsedMilliseconds -gt 15000) {{
          throw ("slow ms=" + $sw.ElapsedMilliseconds)
        }}
        Write-Output ("hostile_ok ms=" + $sw.ElapsedMilliseconds)
        """
    )
    proc = _ps(script, env={"BOBIVERSE_PROGRAMDATA_ROOT": str(pd)}, timeout=60)
    text = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, text
    assert "hostile_ok ms=" in text
