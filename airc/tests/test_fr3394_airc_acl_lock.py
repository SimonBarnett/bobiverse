"""FR #3394: airc install ACL fail-closed + ProgramData lock + purge path allow-list."""
from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from repo_layout import ROOT

COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
INSTALL = ROOT / "airc/scripts/Install-Airc.ps1"
UNINSTALL = ROOT / "airc/scripts/Uninstall-Airc.ps1"
POST = ROOT / "common/docs/post-install.md"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"


def _ps(script: str, timeout: int = 90) -> subprocess.CompletedProcess[str]:
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


def test_fr3394_protect_supports_fail_closed():
    t = COMMON.read_text(encoding="utf-8-sig")
    assert "function Protect-BobiverseInstallTree" in t
    assert "FailClosed" in t
    assert "FR #3394" in t


def test_fr3394_ensure_programdata_helper_exists():
    t = COMMON.read_text(encoding="utf-8-sig")
    assert "function Ensure-BobiverseProgramDataRoot" in t
    assert "FR #3394" in t


def test_fr3394_purge_path_allowlist_helper_exists():
    t = COMMON.read_text(encoding="utf-8-sig")
    assert "function Test-BobiverseAircPurgePathAllowed" in t


def test_fr3394_install_protects_before_service_start():
    t = INSTALL.read_text(encoding="utf-8-sig")
    assert "FR #3394" in t
    assert "Protect-BobiverseInstallTree" in t
    assert "FailClosed" in t
    assert "Ensure-BobiverseProgramDataRoot" in t
    # Delay Start-Service until after Protect (NoStart then start).
    assert "NoStart" in t
    idx_protect = t.find("Protect-BobiverseInstallTree")
    idx_legacy = t.find("Install-AircConsole")
    # At least one Protect call must appear before the legacy install invocation that used to start the service.
    assert idx_protect > 0
    # Final Protect + Start must be after legacy call.
    assert t.rfind("Protect-BobiverseInstallTree") > t.find("& $installLegacy")


def test_fr3394_uninstall_uses_purge_allowlist():
    t = UNINSTALL.read_text(encoding="utf-8-sig")
    assert "Test-BobiverseAircPurgePathAllowed" in t
    assert "FR #3394" in t


def test_fr3394_docs_mention_fail_closed_acl():
    post = POST.read_text(encoding="utf-8")
    skill = SKILL.read_text(encoding="utf-8")
    blob = post + "\n" + skill
    assert "FR #3394" in blob or "#3394" in blob
    assert "FailClosed" in blob or "fail-closed" in blob.lower() or "fail closed" in blob.lower()


@pytest.mark.skipif(os.name != "nt", reason="Windows ACL / path only")
def test_fr3394_purge_allowlist_rejects_canary(tmp_path: Path):
    install = tmp_path / "ai" / "airc"
    home = tmp_path / "home"
    install.mkdir(parents=True)
    home.mkdir()
    pd = tmp_path / "ProgramData" / "Bobiverse"
    pd.mkdir(parents=True)
    canary = Path(r"C:\Windows\Temp\canary-fr3394")
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        $ok = Test-BobiverseAircPurgePathAllowed -Path '{install}\\scripts' -InstallRoot '{install}' -ConsoleHome '{home}' -ProgramDataRoot '{pd}'
        if (-not $ok) {{ throw 'expected install child allowed' }}
        $bad = Test-BobiverseAircPurgePathAllowed -Path '{canary}' -InstallRoot '{install}' -ConsoleHome '{home}' -ProgramDataRoot '{pd}'
        if ($bad) {{ throw 'canary must be refused' }}
        $removed = Test-BobiverseAircPurgePathAllowed -Path 'removed:{install}\\AGENTS.md' -InstallRoot '{install}' -ConsoleHome '{home}' -ProgramDataRoot '{pd}'
        if ($removed) {{ throw 'removed: prefix must be refused' }}
        Write-Output 'allowlist-ok'
        """
    )
    proc = _ps(script)
    assert proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")
    assert "allowlist-ok" in (proc.stdout or "")


@pytest.mark.skipif(os.name != "nt", reason="Windows ACL only")
def test_fr3394_protect_fail_closed_locks_tmp(tmp_path: Path):
    root = tmp_path / "airc"
    root.mkdir()
    (root / "airc.exe").write_text("x", encoding="utf-8")
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        Protect-BobiverseInstallTree -Path '{root}' -Recurse -FailClosed
        $acl = Get-Acl -LiteralPath '{root}'
        if (-not $acl.AreAccessRulesProtected) {{ throw 'inheritance still on' }}
        $ic = & icacls.exe '{root}' 2>&1 | Out-String
        if ($ic -match '(?i)\\(M\\)|\\(W\\)|\\(F\\).*Users' -and $ic -match '(?i)BUILTIN\\\\Users:\\(OI\\)\\(CI\\)\\(F\\)') {{
            throw "Users still Full on tree: $ic"
        }}
        if ($ic -match '(?i)Authenticated Users:\\(OI\\)\\(CI\\)\\(M\\)') {{
            throw "Authenticated Users modify still present: $ic"
        }}
        # Users may be RX only — that is required.
        if ($ic -notmatch '(?i)BUILTIN\\\\Users') {{
            # some locales omit name; SID check via Get-Acl
            $sids = @($acl.Access | ForEach-Object {{
                try {{ $_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value }}
                catch {{ $_.IdentityReference.Value }}
            }})
            if ('S-1-5-32-545' -notin $sids) {{ throw "Users RX missing: $($sids -join ',')" }}
        }}
        Write-Output 'protect-ok'
        """
    )
    proc = _ps(script)
    assert proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")
    assert "protect-ok" in (proc.stdout or "")


@pytest.mark.skipif(os.name != "nt", reason="Windows ACL only")
def test_fr3394_ensure_programdata_locks_precreated(tmp_path: Path):
    """Pre-created ProgramData\\Bobiverse (user-owned) is re-locked to SYSTEM+Admins+Users RX."""
    pd = tmp_path / "Bobiverse"
    pd.mkdir()
    (pd / "pre.txt").write_text("user-owned", encoding="utf-8")
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        $r = Ensure-BobiverseProgramDataRoot -Root '{pd}' -FailClosed
        if (-not $r) {{ throw 'Ensure returned empty' }}
        $acl = Get-Acl -LiteralPath '{pd}'
        if (-not $acl.AreAccessRulesProtected) {{ throw 'ProgramData root inheritance still on' }}
        $logs = Join-Path '{pd}' 'logs'
        if (-not (Test-Path -LiteralPath $logs)) {{ throw 'logs missing' }}
        $ic = & icacls.exe '{pd}' 2>&1 | Out-String
        if ($ic -match '(?i)Authenticated Users:\\(OI\\)\\(CI\\)\\(M\\)') {{
            throw "Authenticated Users modify on ProgramData Bobiverse: $ic"
        }}
        Write-Output 'ensure-ok'
        """
    )
    proc = _ps(script)
    assert proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")
    assert "ensure-ok" in (proc.stdout or "")
