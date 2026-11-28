"""FR #9945: Get-BobiverseChairHost must never assign to $host/$Host."""
from __future__ import annotations

import re
import subprocess
import sys
import textwrap
from pathlib import Path

from repo_layout import ROOT


COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
INSTALL = ROOT / "jeeves" / "scripts" / "Install-Jeeves.ps1"


def _fn_block(src: str, name: str) -> str:
    m = re.search(
        rf"(?ms)^function {re.escape(name)} \{{.*?^\}}\s*$",
        src,
    )
    assert m, f"function {name} not found"
    return m.group(0)


def test_fr9945_get_chair_host_never_assigns_ps_host_var():
    src = COMMON.read_text(encoding="utf-8")
    block = _fn_block(src, "Get-BobiverseChairHost")
    # PowerShell $Host is case-insensitive; any $host= in this function is the bug.
    assert not re.search(r"(?im)\$host\s*=", block), block
    assert "$chairHost" in block
    assert "FR #9945" in block


def test_fr9945_install_jeeves_fail_closed_on_probe_throw():
    src = INSTALL.read_text(encoding="utf-8")
    assert "FR #9945" in src
    assert "leaving ircJeeves untouched" in src
    assert "InstallChairService -eq $true" in src
    assert "InstallChairService -eq $false" in src
    # Disable only on explicit false, not on probe throw / $null
    disable_idx = src.index("Disable-BobiverseStrayChairService -Name $ServiceName")
    elif_false = src.rfind("elseif ($script:InstallChairService -eq $false)", 0, disable_idx)
    assert elif_false > 0


def test_fr9945_get_chair_host_runs_under_powershell():
    """Live repro of the InternalHost throw; fixed body must return walrus."""
    # Extract function from Common and invoke under powershell.exe.
    src = COMMON.read_text(encoding="utf-8")
    block = _fn_block(src, "Get-BobiverseChairHost")
    ps = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        {block}
        $r = Get-BobiverseChairHost
        if ($r -ne 'walrus' -and $r -ne $env:JEEVES_CHAIR_HOST) {{
          # allow env override when set
        }}
        Write-Output ("OK:" + $r.GetType().FullName + ":" + $r)
        """
    )
    # Force empty env chair host for default path
    env = dict(**{k: v for k, v in __import__("os").environ.items()})
    env.pop("JEEVES_CHAIR_HOST", None)
    proc = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            ps,
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, out
    assert "OK:System.String:walrus" in out.replace("\r", ""), out
    assert "InternalHost" not in out
    assert "read-only" not in out.lower()
