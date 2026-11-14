"""FR #7256: Ensure-BobiverseGithubToken copies operator console github.token as SYSTEM."""
from __future__ import annotations

import subprocess
from pathlib import Path

from repo_layout import ROOT

COMMON_PS1 = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"


def _ps(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_fr7256_ensure_copies_interactive_profile_token(tmp_path: Path):
    """USERPROFILE=systemprofile has no token; operator home does (LastLoggedOn / override)."""
    install = tmp_path / "bob"
    (install / "config").mkdir(parents=True)
    sys_home = tmp_path / "Windows" / "systemprofile"
    sys_home.mkdir(parents=True)
    op = tmp_path / "Users" / "FleetAdmin7256"
    tok_path = op / ".grok" / "bob" / "github.token"
    tok_path.parent.mkdir(parents=True)
    fake = "FAKE_GH_TOKEN_7256_INTERACTIVE"
    tok_path.write_text(fake + "\n", encoding="utf-8")
    ps = f"""
$ErrorActionPreference = 'Stop'
. '{COMMON_PS1}'
$env:GH_TOKEN = ''
$env:GITHUB_TOKEN = ''
$env:USERPROFILE = '{sys_home}'
$env:SystemDrive = '{tmp_path}'
$env:BOB_GROK_WEEKLY_USER_HOME = '{op}'
$env:PATH = 'C:\\Windows\\System32'
$r = Ensure-BobiverseGithubToken -InstallRoot '{install}'
if (-not $r.Ok) {{ throw ('Ensure failed source=' + $r.Source) }}
if ($r.Source -ne 'file:interactive/.grok/bob/github.token') {{ throw ('bad source=' + $r.Source) }}
$checked = @($r.Checked) -join ','
if ($checked -notmatch 'interactive') {{ throw ('checked missing interactive: ' + $checked) }}
if ($checked -match 'FAKE_') {{ throw 'token leaked into Checked' }}
Write-Output ('ok source=' + $r.Source)
"""
    proc = _ps(ps)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "ok source=file:interactive/.grok/bob/github.token" in proc.stdout
    assert fake not in proc.stdout
    written = (install / "config" / "github.token").read_text(encoding="utf-8").strip()
    assert written == fake


def test_fr7256_ensure_reads_interactive_stamp_when_override_empty(tmp_path: Path):
    install = tmp_path / "bob"
    (install / "config").mkdir(parents=True)
    (install / "run").mkdir(parents=True)
    sys_home = tmp_path / "Windows" / "systemprofile"
    sys_home.mkdir(parents=True)
    op = tmp_path / "Users" / "Parked7256"
    tok_path = op / ".grok" / "bob" / "github.token"
    tok_path.parent.mkdir(parents=True)
    fake = "FAKE_GH_TOKEN_7256_STAMP"
    tok_path.write_text(fake + "\n", encoding="utf-8")
    (install / "run" / "interactive-user-home.txt").write_text(str(op) + "\n", encoding="utf-8")
    ps = f"""
$ErrorActionPreference = 'Stop'
. '{COMMON_PS1}'
$env:GH_TOKEN = ''
$env:GITHUB_TOKEN = ''
$env:USERPROFILE = '{sys_home}'
$env:SystemDrive = '{tmp_path}'
$env:BOB_GROK_WEEKLY_USER_HOME = ''
$env:BOBIVERSE_SKIP_LIVE_INTERACTIVE_HOME = '1'
$env:PATH = 'C:\\Windows\\System32'
$r = Ensure-BobiverseGithubToken -InstallRoot '{install}'
if (-not $r.Ok) {{ throw ('Ensure failed source=' + $r.Source) }}
if ($r.Source -ne 'file:interactive/.grok/bob/github.token') {{ throw ('bad source=' + $r.Source) }}
Write-Output ('ok source=' + $r.Source)
"""
    proc = _ps(ps)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert fake not in proc.stdout
    written = (install / "config" / "github.token").read_text(encoding="utf-8").strip()
    assert written == fake


def test_fr7256_helper_exists_in_common():
    text = COMMON_PS1.read_text(encoding="utf-8-sig")
    assert "function Get-BobiverseInteractiveUserHome" in text
    assert "FR #7256" in text
    assert "LastLoggedOnUser" in text
    assert "file:interactive/.grok/bob/github.token" in text
    assert "gh auth token" in text
