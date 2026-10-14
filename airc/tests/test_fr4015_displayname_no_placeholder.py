"""FR #4015: nssm DisplayName must never show unsubstituted #machine."""
from __future__ import annotations

import re

from repo_layout import ROOT

INSTALL = (ROOT / "airc" / "scripts" / "Install-AircConsole.ps1").read_text(encoding="utf-8-sig")
OPS = (ROOT / "airc" / "docs" / "airc-ops.md").read_text(encoding="utf-8-sig")


def test_fr4015_no_literal_machine_fallback():
    # The bug: else { 'machine' } -> DisplayName "airc console (#machine IRC shell)"
    assert "else { 'machine' }" not in INSTALL
    assert 'else { "machine" }' not in INSTALL
    assert ("FR #4015" in INSTALL) or ("#4015" in INSTALL)


def test_fr4015_displayname_uses_resolved_id_or_computername():
    assert "$displayName" in INSTALL
    assert "dnMachine" in INSTALL
    # Must expand from MachineId / script id / sanitized COMPUTERNAME
    assert "COMPUTERNAME" in INSTALL
    assert re.search(
        r'\$displayName\s*=\s*"airc console \(#\$\{dnMachine\} IRC shell\)"',
        INSTALL,
    )
    # Never leave a static #machine token in the script as the display string
    assert "airc console (#machine IRC shell)" not in INSTALL
    assert "airc console (#{machine} IRC shell)" not in INSTALL


def test_fr4015_description_same_resolution():
    assert "nick console on #${dnMachine}" in INSTALL or 'nick console on #${dnMachine}' in INSTALL


def test_fr4015_ops_documents():
    assert "FR #4015" in OPS
