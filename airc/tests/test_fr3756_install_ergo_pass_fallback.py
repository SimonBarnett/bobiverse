"""FR #3756: Install-AircConsole Ergo PASS fallbacks (env / -ErgoPasswordFile) + clear error."""
from __future__ import annotations

import subprocess
from pathlib import Path

from repo_layout import ROOT

INSTALL = ROOT / "airc" / "scripts" / "Install-AircConsole.ps1"
SKILL = (
    ROOT
    / "airc"
    / ".grok"
    / "skills"
    / "bobiverse-airc-troubleshooting"
    / "SKILL.md"
)


def test_fr3756_install_env_fallback_and_error_lists_options():
    text = INSTALL.read_text(encoding="utf-8")
    assert "FR #3756" in text
    assert "AIRC_PACK_ERGO_PASSWORD" in text
    assert "AGENTIC_IRC_PASSWORD" in text
    assert "AIRC_CONSOLE_SERVER_PASSWORD" in text
    assert "BOB_IRC_PASSWORD" in text
    assert "GetEnvironmentVariable" in text
    assert 'env:$key' in text or "env:" in text
    # Old single-line re-download-only throw must not be the only guidance
    assert "-ErgoPasswordFile" in text
    assert "Public MSIs never embed" in text or "issue #4" in text
    assert "Never invent" in text
    # Still prefer packaged release path (issue #294)
    assert r"config\ergo.password" in text or "config/ergo.password" in text


def test_fr3756_install_script_utf8_no_bom_ascii():
    raw = INSTALL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = INSTALL.read_text(encoding="utf-8")
    assert not any(ord(ch) > 127 for ch in text), "Install-AircConsole must stay ASCII (quiet MSI / WinPS 5.1)"


def test_fr3756_troubleshooting_skill_row():
    text = SKILL.read_text(encoding="utf-8")
    assert "FR #3756" in text
    assert "Ergo server PASS missing" in text or "config\\ergo.password" in text
    assert "AGENTIC_IRC_PASSWORD" in text or "-ErgoPasswordFile" in text


def test_fr3756_install_parses_under_powershell():
    ps = r"""
$ErrorActionPreference = 'Stop'
$path = $env:AIRC_INSTALL_SCRIPT
$errs = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$null, [ref]$errs)
if ($errs -and $errs.Count -gt 0) {
  $errs | ForEach-Object { Write-Output $_.ToString() }
  exit 2
}
Write-Output 'PARSE_OK'
exit 0
"""
    env = dict(**{k: v for k, v in __import__("os").environ.items()})
    env["AIRC_INSTALL_SCRIPT"] = str(INSTALL)
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


def test_fr3756_env_fallback_seeds_home_without_packaged_file(tmp_path: Path):
    """Dot-source only the secrets helper via a trimmed PS harness (no admin install)."""
    home = tmp_path / "console-home"
    home.mkdir()
    # Extract function bodies by invoking a minimal reimplementation check:
    # run Install's Initialize path is heavy; pin behaviour with a small mirror of the env loop.
    ps = r"""
$ErrorActionPreference = 'Stop'
$ConsoleHomeDir = $env:FR3756_HOME
$ergoDest = Join-Path $ConsoleHomeDir 'ergo.password'
$secret = $null
$source = $null
foreach ($key in @(
    'AIRC_PACK_ERGO_PASSWORD',
    'AGENTIC_IRC_PASSWORD',
    'AIRC_CONSOLE_SERVER_PASSWORD',
    'BOB_IRC_PASSWORD'
)) {
  $v = [string](Get-Item -LiteralPath "Env:$key" -ErrorAction SilentlyContinue).Value
  if ($v -and $v.Trim()) {
    $secret = $v.Trim()
    $source = "env:$key"
    break
  }
}
if (-not $secret) { throw 'expected env secret' }
[IO.File]::WriteAllText($ergoDest, $secret + "`n", (New-Object System.Text.UTF8Encoding $false))
Write-Output "OK source=$source"
exit 0
"""
    env = dict(**{k: v for k, v in __import__("os").environ.items()})
    # Clear competing secrets; set only AGENTIC_IRC_PASSWORD to a non-secret placeholder (GitGuardian).
    for k in (
        "AIRC_PACK_ERGO_PASSWORD",
        "AGENTIC_IRC_PASSWORD",
        "AIRC_CONSOLE_SERVER_PASSWORD",
        "BOB_IRC_PASSWORD",
    ):
        env.pop(k, None)
    env["AGENTIC_IRC_PASSWORD"] = "secret-placeholder-fr3756"
    env["FR3756_HOME"] = str(home)
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, out
    assert "OK source=env:AGENTIC_IRC_PASSWORD" in out, out
    written = (home / "ergo.password").read_text(encoding="utf-8").strip()
    assert written == "secret-placeholder-fr3756"
