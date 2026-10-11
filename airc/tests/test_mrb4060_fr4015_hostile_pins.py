"""Hostile pins for MRB #4060 / FR #4015 (additive after product merge)."""
from __future__ import annotations

from repo_layout import ROOT

INSTALL = (ROOT / "airc" / "scripts" / "Install-AircConsole.ps1").read_text(encoding="utf-8-sig")


def test_mrb4060_local_last_resort_contiguous():
    idx = INSTALL.find("FR #4015")
    chunk = INSTALL[idx : idx + 900]
    assert "dnMachine = 'local'" in chunk or 'dnMachine = "local"' in chunk
    assert "COMPUTERNAME" in chunk
    assert "else { 'machine' }" not in INSTALL


def test_mrb4060_displayname_format_uses_dnMachine():
    assert 'airc console (#${dnMachine} IRC shell)' in INSTALL
    assert "airc console (#machine IRC shell)" not in INSTALL