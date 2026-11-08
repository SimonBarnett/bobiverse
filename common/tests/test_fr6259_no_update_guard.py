"""FR #6259: BOBIVERSE_NO_UPDATE=1 must suppress Sync + Update before side effects.

Root cause class: Start-Bob / Sync compared $env:BOBIVERSE_NO_UPDATE exactly to '1'
(no Trim). NSSM AppEnvironmentExtra / REG_MULTI_SZ often carries trailing CR/space, so
Sync still ran (ff / older-overwrite refuse) while Update (which Trimmed) skipped.
Start wrappers also always invoked Update even when the guard was on.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import REPO

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="windows PowerShell harness")

COMMON = REPO / "common" / "scripts" / "Bobiverse-Common.ps1"
SYNC = REPO / "common" / "scripts" / "Sync-BobiverseFromRepo.ps1"
UPDATE = REPO / "common" / "scripts" / "Update-BobiverseService.ps1"


def _t(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8-sig")


def _ps(script: str, env: dict | None = None, timeout: int = 60) -> subprocess.CompletedProcess:
    e = {k: v for k, v in os.environ.items()}
    if env:
        e.update(env)
    # Drop conflicting values unless the test sets them.
    for k in list(e):
        if k in ("BOBIVERSE_NO_UPDATE", "BOB_AUTOUPDATE") and (not env or k not in env):
            e.pop(k, None)
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        env=e,
        timeout=timeout,
    )


def test_helper_exists_and_trims_process_value():
    assert "function Get-BobiverseNoUpdateReason" in _t("common/scripts/Bobiverse-Common.ps1")
    script = rf"""
. '{COMMON}'
$env:BOBIVERSE_NO_UPDATE = '1 '
$r = Get-BobiverseNoUpdateReason
if (-not $r) {{ throw 'expected guard effective for padded 1' }}
Write-Output "REASON=$r"
$env:BOBIVERSE_NO_UPDATE = '0'
$r2 = Get-BobiverseNoUpdateReason
if ($r2) {{ throw 'expected null for 0' }}
Write-Output 'OK'
"""
    p = _ps(script, env={"BOBIVERSE_NO_UPDATE": "1 "})
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert "REASON=BOBIVERSE_NO_UPDATE=1" in p.stdout
    assert "OK" in p.stdout


def test_helper_absent_and_empty_are_disabled():
    script = rf"""
. '{COMMON}'
Remove-Item Env:BOBIVERSE_NO_UPDATE -ErrorAction SilentlyContinue
$r = Get-BobiverseNoUpdateReason
if ($r) {{ throw "unexpected $r" }}
$env:BOBIVERSE_NO_UPDATE = ''
$r2 = Get-BobiverseNoUpdateReason
if ($r2) {{ throw "unexpected empty $r2" }}
Write-Output 'OK'
"""
    p = _ps(script, env={})
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert "OK" in p.stdout


@pytest.mark.skipif(not shutil.which("git"), reason="git harness")
def test_sync_skips_when_guard_has_trailing_whitespace(tmp_path):
    """Regression for the Slab activation failure class: padded =1 must not sync."""
    install = tmp_path / "bob"
    install.mkdir()
    (install / "VERSION").write_text("0.0.1\n", encoding="utf-8")
    script = rf"""
$env:BOBIVERSE_NO_UPDATE = "1`r "
& '{SYNC}' -Product bob -InstallRoot '{install}' -DryRun
exit $LASTEXITCODE
"""
    p = _ps(script, env={"BOBIVERSE_NO_UPDATE": "1\r "})
    text = (p.stdout or "") + (p.stderr or "")
    assert p.returncode == 0, text
    assert "sync-skip" in text and "BOBIVERSE_NO_UPDATE=1" in text
    assert "would bootstrap" not in text
    assert "worktree-dry-run" not in text


@pytest.mark.parametrize(
    "rel,prod,svc",
    [
        ("bob/scripts/Start-Bob.ps1", "bob", "ircBob"),
        ("jeeves/scripts/Start-Jeeves.ps1", "jeeves", "ircJeeves"),
    ],
)
def test_start_wrappers_suppress_sync_and_updater_invocation(rel, prod, svc):
    t = _t(rel)
    assert "Get-BobiverseNoUpdateReason" in t
    assert "no-update-guard seen=1 effective=1" in t
    assert "sync=suppressed updater=suppressed" in t
    # Both side-effect scripts only appear inside the else (guard absent) path.
    body = re.sub(r"<#.*?#>", "", t, flags=re.S)
    body = "\n".join(l for l in body.splitlines() if not l.lstrip().startswith("#"))
    assert "Get-BobiverseNoUpdateReason" in body
    i_guard = body.index("Get-BobiverseNoUpdateReason")
    i_sync = body.index("& $sync")
    i_upd = body.index("& $updater")
    assert i_guard < i_sync < i_upd
    # Exact-eq gate without Trim must be gone from the start wrapper.
    assert "$env:BOBIVERSE_NO_UPDATE -ne '1'" not in t
    assert "$env:BOBIVERSE_NO_UPDATE -eq '1'" not in t
    assert f"-Product {prod}" in t and f"-ServiceName {svc}" in t


def test_start_airc_uses_shared_no_update_helper():
    t = _t("airc/scripts/Start-AircConsole.ps1")
    assert "Get-BobiverseNoUpdateReason" in t
    assert "no-update-guard" in t
    assert "$env:BOBIVERSE_NO_UPDATE -eq '1'" not in t
    # Sync / Update remain gated by policy flags (already false when guard on).
    assert "& $sync -Product airc" in t
    assert "& $updater -Product airc" in t


def test_sync_script_uses_shared_helper_before_side_effects():
    t = _t("common/scripts/Sync-BobiverseFromRepo.ps1")
    assert "Get-BobiverseNoUpdateReason" in t
    body = re.sub(r"<#.*?#>", "", t, flags=re.S)
    body = "\n".join(l for l in body.splitlines() if not l.lstrip().startswith("#"))
    i_guard = body.index("Get-BobiverseNoUpdateReason")
    i_exit = body.index("exit 0", i_guard)
    # After the guard exit, Sync resolves InstallRoot / touches git or robocopy.
    tail = body[i_exit:]
    assert "Get-BobiverseProductRoot" in tail or "Ensure-BobiverseInstallWorkTree" in tail or "robocopy" in tail.lower()
    assert "$env:BOBIVERSE_NO_UPDATE -eq '1'" not in body


def test_updater_optout_uses_shared_helper():
    t = _t("common/scripts/Update-BobiverseService.ps1")
    assert "Get-BobiverseNoUpdateReason" in t
    assert "function Get-OptOutReason" in t


def test_docs_mention_fr6259_trim_contract():
    t = _t("common/docs/post-install.md")
    assert "FR #6259" in t
    assert "AppEnvironmentExtra" in t or "Trim" in t or "trim" in t.lower()
