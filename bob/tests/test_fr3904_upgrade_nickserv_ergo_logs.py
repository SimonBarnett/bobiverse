"""FR #3904: bob upgrade must keep Ergo PASS + nickserv, log stdout, surface NICKNAME_RESERVED.

flamingo 0.1.22 -> 0.1.30 left ircBob Running with empty home\\nickserv.password,
no config\\ergo.password (sibling airc had one), and no NSSM AppStdout — so the
NICKNAME_RESERVED loop was invisible.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from repo_layout import ROOT

COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
INSTALL = ROOT / "bob" / "scripts" / "Install-Bob.ps1"
START = ROOT / "bob" / "scripts" / "Start-Bob.ps1"
IRC_AGENT = ROOT / "common" / "scripts" / "irc_agent.py"
POST = ROOT / "common" / "docs" / "post-install.md"
TROUBLE = (
    ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-troubleshooting" / "SKILL.md"
)
PS = shutil.which("powershell.exe") or shutil.which("powershell")
win = pytest.mark.skipif(os.name != "nt" or not PS, reason="needs Windows PowerShell")


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr3904_ergo_path_checks_sibling_airc_jeeves():
    t = _read(COMMON)
    assert "function Get-BobiverseErgoPasswordPath" in t
    # Sibling product config (flamingo: airc had PASS, bob did not).
    assert r"airc\config\ergo.password" in t or "airc/config/ergo.password" in t
    assert r"jeeves\config\ergo.password" in t or "jeeves/config/ergo.password" in t
    assert "FR #3904" in t


def test_fr3904_install_sets_appstdout_and_preserves_prior_bobhome():
    t = _read(INSTALL)
    assert "FR #3904" in t
    assert "AppStdout" in t
    assert "AppStderr" in t
    assert "AppStdoutCreationDisposition" in t
    # Must read prior AppParameters BEFORE Remove-BobiverseService (airc #1552 pattern).
    # Match the live call, not the FR #3904 comment that also names Remove-*.
    i_prior = t.find("$priorAppParams = Get-BobiverseServiceAppParameters")
    i_remove = t.find("Remove-BobiverseService -Nssm")
    assert i_prior > 0 and i_remove > 0 and i_prior < i_remove
    assert "BobHome" in t[i_prior : i_prior + 1200]
    # NickServ migrate + fail-closed on upgrade.
    assert "nickserv.password" in t
    assert "Ensure-BobiverseBobNickServPassword" in t or "Sync-BobiverseBobNickServ" in t
    assert "1603" in t or "fail" in t.lower()


def test_fr3904_install_seeds_ergo_from_sibling_or_docs():
    t = _read(INSTALL)
    assert "Import-BobiverseErgoPassword" in t or "Get-BobiverseErgoPasswordPath" in t
    # Seed install config when found from sibling so next start does not depend on airc.
    assert "Seed-BobiverseErgoPassword" in t or "Copy-Item" in t or "ergo.password" in t


def test_fr3904_irc_agent_surfaces_nickname_reserved():
    t = IRC_AGENT.read_text(encoding="utf-8")
    assert "NICKNAME_RESERVED" in t
    # Must call crash_report on reserved-nick abort (not silent forever reconnect).
    assert "report_exception" in t or "crash_report" in t
    # Pin FR so hostile MRB can find the gate.
    assert "3904" in t or "FR #3904" in t


def test_fr3904_docs_and_troubleshooting():
    post = POST.read_text(encoding="utf-8")
    assert "FR #3904" in post or "sibling" in post.lower()
    assert "AppStdout" in post or "logs\\stdout.log" in post or "logs/stdout.log" in post
    assert "ergo.password" in post
    assert "nickserv.password" in post
    tr = TROUBLE.read_text(encoding="utf-8")
    assert "FR #3904" in tr or "AppStdout" in tr or "logs\\stdout" in tr


@win
def test_fr3904_ergo_path_resolves_sibling_airc(tmp_path: Path):
    """Live: Get-BobiverseErgoPasswordPath finds sibling airc when bob config is empty."""
    ai = tmp_path / "ai"
    bob = ai / "bob"
    airc = ai / "airc"
    (bob / "config").mkdir(parents=True)
    (airc / "config").mkdir(parents=True)
    secret = "secret-placeholder-fr3904-ergo"
    (airc / "config" / "ergo.password").write_text(secret + "\n", encoding="utf-8")
    ps = r"""
$ErrorActionPreference = 'Stop'
. $env:FR3904_COMMON
$p = Get-BobiverseErgoPasswordPath -InstallRoot $env:FR3904_BOB -HomeDir (Join-Path $env:FR3904_BOB 'home')
if (-not $p) { Write-Output 'FAIL no-path'; exit 2 }
$got = (Get-Content -LiteralPath $p -Raw).Trim()
if ($got -ne $env:FR3904_SECRET) { Write-Output "FAIL got-len=$($got.Length)"; exit 3 }
Write-Output "OK path=$p"
exit 0
"""
    env = dict(os.environ)
    env["FR3904_COMMON"] = str(COMMON)
    env["FR3904_BOB"] = str(bob)
    env["FR3904_SECRET"] = secret
    # Clear env PASS so Import path is unused; we only test Get-*.
    env.pop("BOB_IRC_PASSWORD", None)
    env.pop("AGENTIC_IRC_PASSWORD", None)
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, out
    assert "OK path=" in out, out
    assert "airc" in out.lower(), out


@win
def test_fr3904_nickserv_migrate_from_profile_bobiverse(tmp_path: Path):
    """Live: Ensure-BobiverseBobNickServPassword copies from %.bobiverse into install home."""
    bob = tmp_path / "bob"
    home = bob / "home"
    legacy = tmp_path / "profile" / ".bobiverse"
    home.mkdir(parents=True)
    legacy.mkdir(parents=True)
    secret = "secret-placeholder-fr3904-ns"
    (legacy / "nickserv.password").write_text(secret + "\n", encoding="utf-8")
    ps = r"""
$ErrorActionPreference = 'Stop'
. $env:FR3904_COMMON
$dest = Join-Path $env:FR3904_BOB 'home'
$r = Ensure-BobiverseBobNickServPassword -BobHome $dest -InstallRoot $env:FR3904_BOB `
  -LegacyHomes @($env:FR3904_LEGACY) -FailIfMissing:$false
if (-not $r.Ok) { Write-Output "FAIL $($r.Reason)"; exit 2 }
$got = (Get-Content -LiteralPath (Join-Path $dest 'nickserv.password') -Raw).Trim()
if ($got -ne $env:FR3904_SECRET) { Write-Output "FAIL len=$($got.Length)"; exit 3 }
Write-Output "OK migrated=$($r.Migrated)"
exit 0
"""
    env = dict(os.environ)
    env["FR3904_COMMON"] = str(COMMON)
    env["FR3904_BOB"] = str(bob)
    env["FR3904_LEGACY"] = str(legacy)
    env["FR3904_SECRET"] = secret
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, out
    assert "OK migrated=" in out, out
    written = (home / "nickserv.password").read_text(encoding="utf-8").strip()
    assert written == secret


@win
def test_fr3904_nickserv_fail_closed_on_upgrade_missing(tmp_path: Path):
    """Live: FailIfMissing throws when upgrade has no nickserv anywhere."""
    bob = tmp_path / "bob"
    home = bob / "home"
    home.mkdir(parents=True)
    # Isolate profile lookups so the live Administrator\\.bobiverse cannot satisfy the probe.
    fake_profile = tmp_path / "empty-profile"
    fake_profile.mkdir()
    fake_sys = tmp_path / "sys"
    (fake_sys / "Users" / "Administrator").mkdir(parents=True)
    ps = r"""
$ErrorActionPreference = 'Stop'
. $env:FR3904_COMMON
try {
  $null = Ensure-BobiverseBobNickServPassword -BobHome (Join-Path $env:FR3904_BOB 'home') `
    -InstallRoot $env:FR3904_BOB -LegacyHomes @() -FailIfMissing
  Write-Output 'FAIL expected-throw'
  exit 2
} catch {
  Write-Output 'OK threw'
  exit 0
}
"""
    env = dict(os.environ)
    env["FR3904_COMMON"] = str(COMMON)
    env["FR3904_BOB"] = str(bob)
    env["USERPROFILE"] = str(fake_profile)
    env["SystemDrive"] = str(fake_sys)
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, out
    assert "OK threw" in out, out


@win
def test_fr3904_install_parses_under_powershell():
    ps = r"""
$ErrorActionPreference = 'Stop'
$path = $env:FR3904_INSTALL
$errs = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$null, [ref]$errs)
if ($errs -and $errs.Count -gt 0) {
  $errs | ForEach-Object { Write-Output $_.ToString() }
  exit 2
}
Write-Output 'PARSE_OK'
exit 0
"""
    env = dict(os.environ)
    env["FR3904_INSTALL"] = str(INSTALL)
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, out
    assert "PARSE_OK" in out, out
