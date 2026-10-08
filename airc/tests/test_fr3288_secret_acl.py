"""FR #3288: Protect-BobiverseSecretPath locks secrets to SYSTEM + Administrators only."""
from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
COMMON = REPO / "common" / "scripts" / "Bobiverse-Common.ps1"
INSTALL_CONSOLE = REPO / "airc" / "scripts" / "Install-AircConsole.ps1"


def _ps(script: str) -> subprocess.CompletedProcess[str]:
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
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows ACL only")
def test_protect_bobiverse_secret_path_strips_users(tmp_path: Path):
    """Protect files while parent stays traversable so Medium-IL can still Get-Acl.

    Recurse-locking a directory first blocks Medium-IL tokens from reading child
    ACLs (Administrators ACE is deny-only until High IL). Installers run elevated.
    """
    secret = tmp_path / "ergo.password"
    secret.write_text("dummy-not-a-real-secret\n", encoding="utf-8")
    # Never name a PowerShell var $home - automatic $HOME is read-only (FR #259 / #2499).
    console_home = tmp_path / "console-home"
    console_home.mkdir()
    files = [
        console_home / "console.password",
        console_home / "operators.txt",
        console_home / "accounts.json",
    ]
    for f in files:
        f.write_text("dummy\n", encoding="utf-8")

    file_paths_ps = ", ".join(f"'{p}'" for p in [secret, *files])
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        $consoleHome = '{console_home}'
        $filePaths = @({file_paths_ps})
        function Assert-SecretAcl([string]$p) {{
            $acl = Get-Acl -LiteralPath $p
            if (-not $acl.AreAccessRulesProtected) {{ throw "not protected: $p" }}
            $sids = @($acl.Access | ForEach-Object {{
                try {{ $_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value }}
                catch {{ $_.IdentityReference.Value }}
            }})
            $ok = @('S-1-5-18', 'S-1-5-32-544')
            foreach ($s in $sids) {{
                if ($s -notin $ok) {{ throw "unexpected SID $s on $p (sids=$($sids -join ','))" }}
            }}
            foreach ($need in $ok) {{
                if ($need -notin $sids) {{ throw "missing $need on $p" }}
            }}
            $ic = & icacls.exe $p 2>&1 | Out-String
            if ($ic -match '(?i)BUILTIN\\\\Users|Authenticated Users|Everyone|CREATOR OWNER') {{
                throw "icacls still shows broad principal on $p : $ic"
            }}
        }}
        foreach ($p in $filePaths) {{
            Protect-BobiverseSecretPath -Path $p
            Assert-SecretAcl $p
        }}
        Protect-BobiverseSecretPath -Path $consoleHome
        Assert-SecretAcl $consoleHome
        $denied = $false
        try {{ Get-Content -LiteralPath '{secret}' -ErrorAction Stop | Out-Null }} catch {{ $denied = $true }}
        if (-not $denied) {{
            # FR #3583: WindowsIdentity.Groups never contains the mandatory integrity
            # label (that lives in TokenIntegrityLevel / whoami Label). Use IsInRole.
            $id = [Security.Principal.WindowsIdentity]::GetCurrent()
            $elevated = ([Security.Principal.WindowsPrincipal]$id).IsInRole(
                [Security.Principal.WindowsBuiltInRole]::Administrator)
            if (-not $elevated) {{
                throw 'expected Get-Content access denied for Medium-IL / non-admin token'
            }}
            # Elevated admin keeps FullControl — read success is OK; ACLs already asserted.
            Write-Output 'READ_OK_ELEVATED'
        }} else {{
            Write-Output 'READ_DENIED'
        }}
        Write-Output 'ACL_OK'
        """
    )
    r = _ps(script)
    assert r.returncode == 0, r.stdout + "\n" + r.stderr
    out = r.stdout or ""
    assert "ACL_OK" in out
    assert ("READ_DENIED" in out) or ("READ_OK_ELEVATED" in out)

@pytest.mark.skipif(os.name != "nt", reason="Windows ACL only")
def test_write_airc_secret_file_source_has_no_username_grant():
    text = INSTALL_CONSOLE.read_text(encoding="utf-8")
    assert "Protect-BobiverseSecretPath" in text
    # Old grant to installing user must be gone from Write-AircSecretFile.
    assert 'icacls $Path /grant ("{0}:(R)" -f $env:USERNAME)' not in text
    assert "env:USERNAME):(R)" not in text.replace(" ", "")


@pytest.mark.skipif(os.name != "nt", reason="Windows only")
def test_install_airc_console_defaults_localsystem_to_install_home():
    text = INSTALL_CONSOLE.read_text(encoding="utf-8")
    assert "FR #3288 install\\home" in text or "FR #3288 install\\home" in text.replace("/", "\\")
    assert "using existing Admin ConsoleHome" not in text
    assert "Remove-AircDefaultProfileSecrets" in text
    assert "MigrateAnyUserProfile" in text


@pytest.mark.skipif(os.name != "nt", reason="Windows only")
def test_protect_helper_exists_in_common():
    text = COMMON.read_text(encoding="utf-8")
    assert "function Protect-BobiverseSecretPath" in text
    assert "S-1-5-18" in text
    assert "S-1-5-32-544" in text


def test_fr3583_elevation_check_uses_isinrole_not_groups_integrity():
    """FR #3583: do not look up High-IL via WindowsIdentity.Groups (always empty)."""
    text = Path(__file__).read_text(encoding="utf-8")
    assert "WindowsBuiltInRole]::Administrator" in text
    assert "IsInRole" in text
    assert "READ_OK_ELEVATED" in text
    # Scan only the embedded Protect script (not this assert helper).
    embed = text[text.find("$denied = $false") : text.find("Write-Output 'ACL_OK'")]
    assert "IsInRole" in embed
    assert "WindowsBuiltInRole" in embed
    assert "$id.Groups" not in embed
    assert ("S-1-16-" + "12288") not in embed
