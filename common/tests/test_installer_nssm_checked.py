"""Installer bug: nssm install/set exit codes were ignored; SCM delete-pending was not awaited (-> 1603)."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from repo_layout import ROOT  # t773u: split repo; legacy flat paths resolve per service

S = ROOT / "scripts"
PS = shutil.which("powershell.exe") or shutil.which("pwsh")


def _t(name: str) -> str:
    return (S / name).read_text(encoding="utf-8-sig")


@pytest.mark.parametrize("name", ["Install-Bob.ps1", "Install-Jeeves.ps1"])
def test_install_and_set_use_checked_nssm(name):
    t = _t(name)
    for line in t.splitlines():
        s = line.strip()
        if s.startswith("[void](Invoke-BobiverseNssm ") and ("'install'" in s or "'set'" in s):
            raise AssertionError(f"{name}: unchecked nssm install/set: {s}")
    assert "Invoke-BobiverseNssmChecked -Exe $Nssm -NssmArgs @('install'" in t


def test_common_has_delete_pending_wait_and_no_password_echo():
    t = _t("Bobiverse-Common.ps1")
    assert "function Wait-BobiverseServiceGone" in t
    assert "function Test-BobiverseServiceDeletePending" in t
    assert "DeleteFlag" in t
    assert "marked for deletion" in t
    # the checked helper must not echo args after ObjectName (password)
    assert "Select-Object -First 3" in t  # values (password, BOB_IRC_PASSWORD) never echoed


@pytest.mark.skipif(not PS or sys.platform != "win32", reason="needs Windows PowerShell")
def test_checked_helper_throws_on_nonzero_and_hides_password(tmp_path):
    fake = tmp_path / "nssm.cmd"
    fake.write_text("@echo off\r\nexit /b 6\r\n", encoding="ascii")
    ps1 = tmp_path / "t.ps1"
    ps1.write_text(
        f". '{S / 'Bobiverse-Common.ps1'}'\n"
        f"try {{ Invoke-BobiverseNssmChecked -Exe '{fake}' -NssmArgs @('set','svc','ObjectName','.\\\\u','S3cretPw') ; 'NOTHROW' }}\n"
        "catch { 'THROW: ' + $_.Exception.Message }\n",
        encoding="utf-8",
    )
    out = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1)],
        capture_output=True, text=True, timeout=60,
    ).stdout
    assert "THROW:" in out and "(6)" in out
    assert "S3cretPw" not in out
