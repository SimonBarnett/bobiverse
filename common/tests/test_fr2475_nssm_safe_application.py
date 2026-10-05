"""FR #2475: installer must not point NSSM Application at a missing exe; msiexec 1618 serialised."""
from __future__ import annotations

from repo_layout import ROOT

COMMON = (ROOT / "common" / "scripts" / "Bobiverse-Common.ps1").read_text(encoding="utf-8-sig")
# Prefer product Install-Jeeves; fall back to flat scripts/
_ij = ROOT / "jeeves" / "scripts" / "Install-Jeeves.ps1"
if not _ij.is_file():
    _ij = ROOT / "scripts" / "Install-Jeeves.ps1"
INSTALL = _ij.read_text(encoding="utf-8-sig")
UPD = (ROOT / "common" / "scripts" / "Update-BobiverseService.ps1").read_text(encoding="utf-8-sig")


def test_fr2475_common_defines_safe_nssm_application_setter():
    assert "function Set-BobiverseNssmApplicationSafe" in COMMON
    assert "function Get-BobiverseNssmApplication" in COMMON
    assert "keeping previous" in COMMON
    assert "FR #2475" in COMMON or "FR#2475" in COMMON


def test_fr2475_common_serialises_msiexec_and_retries_1618():
    assert "function Invoke-BobiverseMsiexecSerialized" in COMMON
    assert "Global\\bobiverse-msiexec" in COMMON or "Global\bobiverse-msiexec" in COMMON
    assert "1618" in COMMON


def test_fr2475_install_jeeves_uses_safe_application_set():
    assert "Set-BobiverseNssmApplicationSafe" in INSTALL
    assert "jeeves" in INSTALL and "jeeves.exe" in INSTALL
    # Must not blindly nssm set Application to jeevesExe without the safe helper
    # (legacy direct set removed for the exe cutover path).
    assert "FR #2475" in INSTALL or "FR#2475" in INSTALL


def test_fr2475_update_uses_serialized_msiexec_or_1618_retry():
    # Apply path must mention 1618 retry or call the shared serialised helper.
    assert ("Invoke-BobiverseMsiexecSerialized" in UPD) or ("1618" in UPD and "bobiverse-msiexec" in UPD)


def test_fr2475_safe_setter_refuses_missing_path_behaviorally(tmp_path):
    """Hostile MRB #2483: exercise Set-BobiverseNssmApplicationSafe refuse path (no real NSSM)."""
    import subprocess
    import textwrap

    common = (ROOT / "common" / "scripts" / "Bobiverse-Common.ps1").resolve()
    stub = tmp_path / "stub.ps1"
    common_ps = str(common).replace("'", "''")
    stub.write_text(
        textwrap.dedent(
            f"""
            $ErrorActionPreference = 'Stop'
            function Invoke-BobiverseNssmChecked {{
                param($Exe,$NssmArgs)
                return [pscustomobject]@{{ ExitCode = 0; Args = $NssmArgs }}
            }}
            . '{common_ps}'
            function Get-BobiverseNssmApplication {{
                param([string]$ServiceName)
                return 'C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe'
            }}
            $missing = Join-Path $env:TEMP ('no-such-jeeves-' + [guid]::NewGuid().ToString() + '.exe')
            $r = Set-BobiverseNssmApplicationSafe -Nssm 'C:\\nssm\\nssm.exe' -ServiceName 'ircJeeves' -NewApplication $missing
            if ($r.Ok) {{ throw 'expected Ok=false' }}
            if (-not $r.KeptPrevious) {{ throw 'expected KeptPrevious' }}
            if ($r.Application -notmatch 'powershell\\.exe$') {{ throw ('unexpected Application=' + $r.Application) }}
            Write-Output 'REFUSE_OK'
            """
        ),
        encoding="utf-8",
        newline="\n",
    )
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(stub)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, out
    assert "REFUSE_OK" in out, out
