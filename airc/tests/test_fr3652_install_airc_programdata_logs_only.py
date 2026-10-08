"""FR #3652: Install-Airc must not Full-Recurse ACL all of ProgramData\\Bobiverse on upgrade.

Ionos evidence: default Ensure-BobiverseProgramDataRoot (ProtectMode Full) walked
~104k files under update\\bob + update\\jeeves and hung the CA 55+ min with no
install-begin log. Jeeves/bob already use LogsOnly via Get-BobiverseMsiLogDir.
"""
from __future__ import annotations

import os
import re
import subprocess
import textwrap
import time
from pathlib import Path

import pytest

from repo_layout import ROOT

INSTALL = ROOT / "airc/scripts/Install-Airc.ps1"
COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"


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


def test_fr3652_install_airc_source_uses_logs_only_for_programdata():
    t = INSTALL.read_text(encoding="utf-8-sig")
    # Call sites only (not throw-string mentions): ...Ensure-BobiverseProgramDataRoot <args>
    calls = list(
        re.finditer(
            r"(?m)^(?!\s*#).*?\bEnsure-BobiverseProgramDataRoot\b([^\n]*)",
            t,
        )
    )
    assert calls, "expected Ensure-BobiverseProgramDataRoot call sites in Install-Airc.ps1"
    for m in calls:
        args = m.group(1)
        # Skip pure string/throw lines that do not invoke the cmdlet.
        if "-FailClosed" not in args and "-ProtectMode" not in args and "-Root" not in args:
            continue
        assert "LogsOnly" in args, (
            "Install-Airc Ensure-BobiverseProgramDataRoot must use -ProtectMode LogsOnly; "
            f"got: Ensure-BobiverseProgramDataRoot{args}"
        )
        assert "ProtectMode" in args
    assert "FR #3652" in t
    # install-begin must appear before the ProgramData Ensure (so CA log shows progress
    # even if a later protect is slow).
    begin = t.find("install-begin")
    ensure = t.find("Ensure-BobiverseProgramDataRoot -FailClosed -ProtectMode LogsOnly")
    assert begin >= 0 and ensure >= 0
    assert begin < ensure, "Write install-begin before Ensure-BobiverseProgramDataRoot"


@pytest.mark.skipif(os.name != "nt", reason="Windows only")
def test_fr3652_logs_only_does_not_touch_update_bob_pad(tmp_path: Path):
    """Pin: ProgramData lock with fat update\\bob must not rewrite those files and must finish fast."""
    pd = tmp_path / "ProgramDataBobiverse"
    fat = pd / "update" / "bob" / "pad"
    fat.mkdir(parents=True)
    markers = []
    for i in range(80):
        p = fat / f"blob-{i}.bin"
        p.write_bytes(b"y" * 2048)
        markers.append((p, p.stat().st_mtime_ns))

    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        $script:BobiverseProgramDataProtectCache = @{{}}
        $env:BOBIVERSE_PROGRAMDATA_ROOT = '{pd}'
        $sw = [Diagnostics.Stopwatch]::StartNew()
        $null = Ensure-BobiverseProgramDataRoot -Root '{pd}' -FailClosed -ProtectMode LogsOnly
        $sw.Stop()
        if ($sw.Elapsed.TotalSeconds -gt 15) {{
          throw ("LogsOnly protect too slow: " + $sw.Elapsed.TotalSeconds + "s")
        }}
        Write-Output ("logs-only-ok elapsed_s=" + [math]::Round($sw.Elapsed.TotalSeconds, 3))
        """
    )
    t0 = time.perf_counter()
    proc = _ps(script, env={"BOBIVERSE_PROGRAMDATA_ROOT": str(pd)}, timeout=60)
    wall = time.perf_counter() - t0
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0, text
    assert "logs-only-ok" in text
    assert wall < 20.0, f"wall clock {wall}s too slow for LogsOnly"
    # update\\bob pad mtimes must be unchanged (Full -Recurse Set-Acl would touch them).
    for p, mtime in markers:
        assert p.stat().st_mtime_ns == mtime, f"LogsOnly must not touch {p}"
