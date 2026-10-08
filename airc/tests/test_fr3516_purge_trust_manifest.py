"""FR #3516: uninstall purge must not trust manifest install_root/console_home; reset ProgramData owner."""
from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from repo_layout import ROOT

COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
UNINSTALL = ROOT / "airc/scripts/Uninstall-Airc.ps1"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"


def _ps(script: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(ROOT),
    )


def test_fr3516_uninstall_ignores_manifest_install_root_for_allowlist():
    t = UNINSTALL.read_text(encoding="utf-8-sig")
    assert "FR #3516" in t
    assert "allowInstall" in t
    assert "allowHome" in t
    assert "ignoring manifest.console_home" in t
    # Must not read planted manifest.install_root into the allow-list base.
    assert "manifest.install_root)" not in t
    assert '$manInstall' not in t
    # Every purge target goes through the allow-list helper.
    assert t.count("Test-BobiverseAircPurgePathAllowed") >= 2


def test_fr3516_common_rejects_drive_root_prefix_and_sets_owner():
    t = COMMON.read_text(encoding="utf-8-sig")
    assert "FR #3516" in t
    assert "Test-BobiverseAircPurgePrefixIsSafe" in t
    # Protect must takeown /A (Administrators) after DACL lock.
    i = t.find("function Protect-BobiverseInstallTree")
    chunk = t[i : i + 4500]
    assert "takeown" in chunk.lower()
    assert "FR #3516" in chunk


@pytest.mark.skipif(os.name != "nt", reason="Windows only")
def test_fr3516_drive_root_install_root_does_not_allow_system32():
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        $bad = Test-BobiverseAircPurgePathAllowed -Path 'C:\\Windows\\System32' -InstallRoot 'C:\\' -ConsoleHome '' -ProgramDataRoot 'C:\\ProgramData\\Bobiverse'
        if ($bad) {{ throw 'C:\\ as InstallRoot must not allow System32' }}
        $still = Test-BobiverseAircPurgePathAllowed -Path 'C:\\Windows\\Temp\\canary' -InstallRoot 'C:\\' -ConsoleHome 'C:\\' -ProgramDataRoot 'C:\\'
        if ($still) {{ throw 'drive-root prefixes must not allow Temp canary' }}
        Write-Output 'drive-root-refused'
        """
    )
    proc = _ps(script)
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0, text
    assert "drive-root-refused" in text


@pytest.mark.skipif(os.name != "nt", reason="Windows only")
def test_fr3516_manifest_evil_install_root_ignored_when_real_root_used(tmp_path: Path):
    """Pin: planted manifest install_root=C:\\ must not expand allow-list; real InstallRoot wins."""
    install = tmp_path / "ai" / "airc"
    home = tmp_path / "console-home"
    install.mkdir(parents=True)
    home.mkdir()
    pd = tmp_path / "ProgramData" / "Bobiverse"
    pd.mkdir(parents=True)
    canary = tmp_path / "WindowsTempCanary"
    canary.mkdir()
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        # Simulate FR #3516 uninstall: allow-list bases = real InstallRoot/ConsoleHome only.
        $InstallRoot = '{install}'
        $keptHome = '{home}'
        $evilManifestInstall = 'C:\\'
        $candidate = '{canary}'
        # Old bug: using evilManifestInstall would allow anything under C:\\
        $withEvil = Test-BobiverseAircPurgePathAllowed -Path $candidate -InstallRoot $evilManifestInstall -ConsoleHome $keptHome -ProgramDataRoot '{pd}'
        $withTrusted = Test-BobiverseAircPurgePathAllowed -Path $candidate -InstallRoot $InstallRoot -ConsoleHome $keptHome -ProgramDataRoot '{pd}'
        if ($withTrusted) {{ throw 'canary outside real install must be refused with trusted bases' }}
        # Drive-root evil base must also refuse (prefix safety).
        if ($withEvil) {{ throw 'even evil C:\\ base must refuse after FR #3516 prefix safety' }}
        $okChild = Test-BobiverseAircPurgePathAllowed -Path (Join-Path $InstallRoot 'config') -InstallRoot $InstallRoot -ConsoleHome $keptHome -ProgramDataRoot '{pd}'
        if (-not $okChild) {{ throw 'real install child must remain allowed' }}
        Write-Output 'manifest-evil-ignored'
        """
    )
    proc = _ps(script)
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0, text
    assert "manifest-evil-ignored" in text


@pytest.mark.skipif(os.name != "nt", reason="Windows ACL only")
def test_fr3516_protect_takeown_best_effort_and_dacl_locks(tmp_path: Path):
    """DACL FailClosed always; takeown /A when elevated (else WARN, still locked)."""
    root = tmp_path / "airc-owned"
    root.mkdir()
    (root / "f.txt").write_text("x", encoding="utf-8")
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        Protect-BobiverseInstallTree -Path '{root}' -Recurse -FailClosed
        $acl = Get-Acl -LiteralPath '{root}'
        if (-not $acl.AreAccessRulesProtected) {{ throw 'inheritance still on' }}
        $id = [Security.Principal.WindowsIdentity]::GetCurrent()
        $p = New-Object Security.Principal.WindowsPrincipal($id)
        $elev = $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        $owner = $acl.Owner
        $sid = $null
        try {{ $sid = ([Security.Principal.NTAccount]$owner).Translate([Security.Principal.SecurityIdentifier]).Value }} catch {{ }}
        if ($elev) {{
          if ($sid -ne 'S-1-5-32-544' -and $owner -notmatch '(?i)Administrators') {{
            throw ("elevated but owner not Administrators: owner=$owner sid=$sid")
          }}
          Write-Output 'owner-ok-elevated'
        }} else {{
          Write-Output 'dacl-ok-takeown-skipped-unelevated'
        }}
        """
    )
    proc = _ps(script)
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0, text
    assert ("owner-ok-elevated" in text) or ("dacl-ok-takeown-skipped-unelevated" in text)


def test_fr3516_skill_mentions_purge_trust():
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3516" in skill or "manifest" in skill.lower()
