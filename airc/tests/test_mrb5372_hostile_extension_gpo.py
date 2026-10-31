"""MRB #5372 hostile pins for EXTENSION GPO ForceInstall (FR #5291)."""
from __future__ import annotations

import inspect

import airc_extension as ex
from repo_layout import ROOT

PS = ROOT / "airc/scripts/Invoke-AircExtensionGpo.ps1"
PY = ROOT / "airc/scripts/airc_extension.py"


def test_mrb5372_no_lgpo_chrome_edge_keys():
    ps = PS.read_text(encoding="utf-8")
    assert "LGPO" not in ps
    assert r"HKLM\Software\Policies\Google\Chrome\ExtensionInstallForcelist" in ps
    assert r"HKLM\Software\Policies\Microsoft\Edge\ExtensionInstallForcelist" in ps
    assert "New-GPLink" in ps
    assert "no_dc" in ps
    assert "password" not in ps.lower() or "Never prints passwords" in ps


def test_mrb5372_service_runner_does_not_block_handler():
    """Parent S4: GPO must not wait on the IRC receive thread."""
    src = inspect.getsource(ex.service_extension_runner)
    compact = "".join(src.split())
    assert "wait=False" in compact
    assert "wait=True" not in compact
    assert "extension_gpo_then_fill_holes" in src


def test_mrb5372_force_install_entry():
    assert ex.FORCE_INSTALL_ENTRY.startswith(ex.DEFAULT_EXTENSION_ID + ";")
    assert "update2/crx" in ex.FORCE_INSTALL_ENTRY
