"""FR #3678: Install-Airc one Full -Recurse; skip takeown when already protected."""
from __future__ import annotations

import os
import re
import subprocess
import textwrap
import time
from pathlib import Path

import pytest

from repo_layout import ROOT

COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
INSTALL = ROOT / "airc/scripts/Install-Airc.ps1"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"
POST = ROOT / "common/docs/post-install.md"


def _ps(script: str, timeout: int = 180) -> subprocess.CompletedProcess[str]:
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
    )


def test_fr3678_install_airc_one_full_recurse_before_start():
    t = INSTALL.read_text(encoding="utf-8-sig")
    assert "FR #3678" in t
    # Early protect (before copy) must NOT pass -Recurse.
    early = t.find("Protect-BobiverseInstallTree -Path $InstallRoot -FailClosed")
    assert early > 0, "expected early root-only Protect without -Recurse"
    early_window = t[early : early + 80]
    assert "-Recurse" not in early_window
    # Exactly one Full -Recurse FailClosed, and it must be after Install-AircConsole.
    recurse_calls = list(
        re.finditer(
            r"Protect-BobiverseInstallTree -Path \$InstallRoot -Recurse -FailClosed",
            t,
        )
    )
    assert len(recurse_calls) == 1, (
        f"expected exactly one Full -Recurse Protect; got {len(recurse_calls)}"
    )
    assert recurse_calls[0].start() > t.find("& $installLegacy")
    assert recurse_calls[0].start() < t.find("Start-Service -Name 'Airc'")


def test_fr3678_common_skips_takeown_when_already_protected():
    t = COMMON.read_text(encoding="utf-8-sig")
    assert "function Test-BobiverseInstallPathProtectedTarget" in t
    assert "FR #3678" in t
    assert "skip takeown" in t.lower()
    assert "elapsed_ms" in t
    # /R still gated on -Recurse (FR #3581 pin must remain).
    assert "$Recurse -and $item.PSIsContainer" in t
    assert "/R /D Y" in t


def test_fr3678_docs_skill_mention():
    skill = SKILL.read_text(encoding="utf-8")
    post = POST.read_text(encoding="utf-8")
    assert "3678" in skill
    assert "3678" in post
    assert "skip" in skill.lower() and "takeown" in skill.lower()


@pytest.mark.skipif(os.name != "nt", reason="Windows ACL only")
def test_fr3678_reprotect_already_locked_tree_fast(tmp_path: Path):
    """Pin: second -Recurse Protect over already-locked tree finishes <10s when elevated.

    Unelevated pytest cannot SetOwner to Administrators, so skip-takeown may not
    arm; accept dacl-ok-unelevated in that case (source pins still cover the gate).
    """
    root = tmp_path / "ai" / "airc"
    root.mkdir(parents=True)
    n = 1000
    for i in range(n):
        sub = root / f"d{i % 40}"
        sub.mkdir(exist_ok=True)
        (sub / f"f-{i}.txt").write_text(f"x{i}\n", encoding="utf-8")

    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        $root = '{root}'
        Protect-BobiverseInstallTree -Path $root -Recurse -FailClosed *>&1 | Out-Null
        $already = Test-BobiverseInstallPathProtectedTarget -Path $root
        if (-not $already) {{
          Write-Output 'dacl-ok-unelevated-skip-timing'
          exit 0
        }}
        $sw = [Diagnostics.Stopwatch]::StartNew()
        $out = Protect-BobiverseInstallTree -Path $root -Recurse -FailClosed *>&1 | Out-String
        $sw.Stop()
        if ($out -notmatch 'FR #3678 skip takeown') {{
          throw ('expected skip takeown on second pass; out=' + $out)
        }}
        if ($sw.Elapsed.TotalSeconds -gt 10) {{
          throw ('second protect too slow s=' + $sw.Elapsed.TotalSeconds)
        }}
        Write-Output ('reprotect-ok elapsed_s=' + [math]::Round($sw.Elapsed.TotalSeconds, 3))
        """
    )
    t0 = time.perf_counter()
    proc = _ps(script, timeout=180)
    wall = time.perf_counter() - t0
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0, text
    assert ("reprotect-ok" in text) or ("dacl-ok-unelevated-skip-timing" in text)
    if "reprotect-ok" in text:
        assert wall < 90.0
