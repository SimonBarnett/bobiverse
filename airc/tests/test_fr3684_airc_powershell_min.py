"""FR #3684: airc client install supports Windows PowerShell 4.0 (Server 2012 R2).

Pins:
- Every *.ps1 on the AIRC_PROFILE=client allow-list has #Requires at most 4.0
- Pack-BobiverseRelease airc MSI declares RegistrySearch + LaunchCondition for >= 4.0
- Docs/skill state the minimum
- Optional: powershell -Version 4 DryRun smoke (skip when host cannot run PS 4.0)
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from repo_layout import ROOT

PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"
COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
POST = ROOT / "common/docs/post-install.md"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"
INSTALL = ROOT / "airc/scripts/Install-Airc.ps1"

# Declared minimum (FR #3684). Keep in sync with Pack LaunchCondition + #Requires.
AIRC_MIN_POWERSHELL = (4, 0)

# Mirrors Get-BobiverseAircClientAllowedScriptNames (*.ps1 only) + install-time
# Install-BootstrapTools (called before client purge when tools opted in / no exe).
CLIENT_PS1_RELATIVE = [
    "common/scripts/Bobiverse-Common.ps1",
    "airc/scripts/Install-Airc.ps1",
    "airc/scripts/Install-AircConsole.ps1",
    "airc/scripts/Uninstall-Airc.ps1",
    "common/scripts/Recover-BobiverseService.ps1",
    "airc/scripts/Resolve-AircConsoleNssm.ps1",
    "airc/scripts/Resolve-AircConsolePython.ps1",
    "airc/scripts/Start-AircConsole.ps1",
    "airc/scripts/Start-AircConsole-Fleet.ps1",
    "common/scripts/Update-BobiverseService.ps1",
    "common/scripts/Report-BobiverseIntakeIssue.ps1",
    "common/scripts/Install-BootstrapTools.ps1",
]

_REQUIRES_RE = re.compile(
    r"(?im)^[ \t]*#Requires[ \t]+-Version[ \t]+(?P<maj>\d+)(?:\.(?P<min>\d+))?"
)


def _no_bom_optional(path: Path) -> None:
    # Client/service scripts may keep UTF-8 BOM (FR #3391 class). Pack generator must not.
    if path.resolve() == PACK.resolve():
        assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path
        return
    # No assertion for BOM on allow-list scripts.
    return


def _parse_requires(text: str) -> tuple[int, int] | None:
    m = _REQUIRES_RE.search(text)
    if not m:
        return None
    maj = int(m.group("maj"))
    minor = int(m.group("min") or "0")
    return maj, minor


def test_client_allowlist_requires_at_most_ps40():
    missing = []
    too_high = []
    for rel in CLIENT_PS1_RELATIVE:
        path = ROOT / rel
        assert path.is_file(), f"missing client-path script {rel}"
        _no_bom_optional(path)
        text = path.read_text(encoding="utf-8-sig")
        req = _parse_requires(text)
        if req is None:
            missing.append(rel)
            continue
        if req > AIRC_MIN_POWERSHELL:
            too_high.append(f"{rel} -> {req[0]}.{req[1]}")
    assert not missing, (
        "client-path *.ps1 must declare #Requires -Version "
        f"{AIRC_MIN_POWERSHELL[0]}.{AIRC_MIN_POWERSHELL[1]} (missing: {missing})"
    )
    assert not too_high, (
        "client-path #Requires must be <= "
        f"{AIRC_MIN_POWERSHELL[0]}.{AIRC_MIN_POWERSHELL[1]}: {too_high}"
    )


def test_common_exports_client_allowlist_includes_install_scripts():
    t = COMMON.read_text(encoding="utf-8-sig")
    assert "Get-BobiverseAircClientAllowedScriptNames" in t
    assert "Install-Airc.ps1" in t
    assert "Bobiverse-Common.ps1" in t
    assert "Report-BobiverseIntakeIssue.ps1" in t


def test_pack_airc_msi_powershell_launch_condition():
    p = PACK.read_text(encoding="utf-8")
    _no_bom_optional(PACK)
    assert "FR #3684" in p or "FR #3684" in p.replace(" ", "")
    assert "POWERSHELLVERSION" in p
    assert "PowerShell\\3\\PowerShellEngine" in p or r"PowerShell\3\PowerShellEngine" in p
    assert "PowerShellVersion" in p
    assert "RegistrySearch" in p
    # LaunchCondition / Condition message + version gate
    assert "requires Windows PowerShell 4.0" in p or 'POWERSHELLVERSION >= "4.0"' in p
    assert 'POWERSHELLVERSION >= "4.0"' in p
    assert "<Condition" in p


def test_docs_and_skill_document_ps40_minimum():
    post = POST.read_text(encoding="utf-8")
    assert "PowerShell 4.0" in post or "powershell 4.0" in post.lower()
    assert "3684" in post or "FR #3684" in post
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3684" in skill
    assert (
        "PowerShell 4.0" in skill
        or "PS 4.0" in skill
        or "#Requires -Version 4.0" in skill
        or "POWERSHELLVERSION" in skill
    )
    inst = INSTALL.read_text(encoding="utf-8-sig")
    assert re.search(r"(?im)^#Requires\s+-Version\s+4(\.0)?\s*$", inst)


def test_optional_ps40_dryrun_smoke():
    """When a PS 4.0 host exists, Install-Airc.ps1 must get past #Requires.

    Marchhare (and most fleet seats) only have 5.1; -Version 4 does not
    downgrade. Skip with an explicit reason when PS 4.0 is unavailable.
    """
    probe = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            # True PS 4 engine only when Major -eq 4 (not 5.1 pretending).
            "if ($PSVersionTable.PSVersion.Major -eq 4) { 'PS4' } "
            "else { 'NOT_PS4:' + $PSVersionTable.PSVersion.ToString() }",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    out = (probe.stdout or "").strip()
    if not out.startswith("PS4"):
        print(
            f"SKIP PS4 DryRun: no PowerShell 4.0 host on this machine "
            f"({out or probe.stderr!r}); FR #3684 pin is source+LaunchCondition only"
        )
        return

    # -WhatIf / missing -DryRun: just parse+Requires by loading as a script block probe.
    # Running full install needs admin + Ergo; only verify #Requires acceptance.
    smoke = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            f"$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile("
            f"'{INSTALL.as_posix()}',[ref]$null,[ref]$e); "
            f"if ($e -and $e.Count) {{ $e | ForEach-Object {{ $_.ToString() }}; exit 2 }}; "
            f"& {{ {INSTALL.read_text(encoding='utf-8-sig').splitlines()[0]} }}; "
            f"Write-Output 'REQUIRES_OK'",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert smoke.returncode == 0, smoke.stdout + smoke.stderr
    assert "REQUIRES_OK" in (smoke.stdout or "")
