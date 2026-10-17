"""FR #4432: airc MSI upgrade must not Error 2613 (REP after deferred CA) or skip stop.

Defects on walrus 1.0.1 upgrade (exit 1603):
1. RemoveExistingProducts after deferred StopAircBeforeUpgrade (Error 2613).
2. Immediate StopAircBeforeValidate set Property=CA id; CAQuietExec64 needs QtExec64CmdLine.
"""

from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
OPS = ROOT / "airc" / "docs" / "airc-ops.md"


def _pack() -> str:
    return PACK.read_text(encoding="utf-8-sig")


def test_fr4432_airc_majorupgrade_after_install_validate():
    text = _pack()
    assert "FR #4432" in text
    assert "majorUpgradeSchedule" in text
    assert "afterInstallValidate" in text
    # airc chooses afterInstallValidate; bob/jeeves keep afterInstallInitialize.
    assert "'afterInstallValidate'" in text or '"afterInstallValidate"' in text
    assert "afterInstallInitialize" in text


def test_fr4432_immediate_stop_uses_qtexec64cmdline():
    text = _pack()
    assert 'Property="QtExec64CmdLine"' in text
    assert "StopAircBeforeValidate" in text
    assert 'Before="InstallValidate"' in text
    # Must not set the CA-named property for the immediate QuietExec (that only feeds deferred CustomActionData).
    assert 'Property="StopAircBeforeValidate"' not in text


def test_fr4432_no_deferred_stop_before_removeexistingproducts():
    text = _pack()
    assert 'CustomAction Id="StopAircBeforeUpgrade"' not in text
    assert 'CustomAction Id="SetStopAircUpgradeCmd"' not in text
    assert 'Action="StopAircBeforeUpgrade"' not in text
    # No Custom Action scheduled Before=RemoveExistingProducts for airc stop.
    assert 'Before="RemoveExistingProducts"' not in text


def test_fr4432_ops_documents_error_2613_and_qtexec():
    text = OPS.read_text(encoding="utf-8-sig")
    assert "FR #4432" in text or "2613" in text
    assert "RemoveExistingProducts" in text or "QtExec64CmdLine" in text
