"""Hostile pins for MRB #4051 / FR #4013 (additive after product merge)."""
from __future__ import annotations

from repo_layout import ROOT

PACK = (ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1").read_text(encoding="utf-8-sig")
COMMON = (ROOT / "common" / "scripts" / "Bobiverse-Common.ps1").read_text(encoding="utf-8-sig")
INSTALL_CMD = (ROOT / "airc" / "scripts" / "Install-Airc.cmd").read_text(encoding="utf-8-sig", errors="replace")


def test_mrb4051_privileged_launchcondition_contiguous():
    idx = PACK.find("FR #4013")
    chunk = PACK[idx : idx + 500]
    assert "Installed OR Privileged" in chunk or "Installed OR Privileged" in PACK
    assert "airc install needs administrator rights" in PACK
    assert 'InstallPrivileges="elevated"' in PACK or "InstallPrivileges=\"elevated\"" in PACK


def test_mrb4051_uac_strips_servicepassword_and_exits_740():
    idx = COMMON.find("function Request-BobiverseUacRelaunch")
    body = COMMON[idx : idx + 2000]
    assert "ServicePassword" in body and "continue" in body
    assert "exit 740" in body
    assert "UAC cancelled" in body or "administrator rights" in body.lower()


def test_mrb4051_cmd_740_before_outer_fail_report():
    i740 = INSTALL_CMD.find('"%EC%"=="740"')
    if i740 < 0:
        i740 = INSTALL_CMD.find("EC%\"==\"740\"")
    report = INSTALL_CMD.find("Report-AircInstallCmdFailure.ps1")
    assert 0 <= i740 < report
    assert "del /f /q \"%FAILFLAG%\"" in INSTALL_CMD or "FAILFLAG" in INSTALL_CMD