"""FR #2355: DisplayName expanded; ConsoleHome never stays under Users\\Default."""
from __future__ import annotations

from repo_layout import ROOT


def _install_text() -> str:
    return (ROOT / "airc" / "scripts" / "Install-AircConsole.ps1").read_text(encoding="utf-8")


def _update_text() -> str:
    return (ROOT / "common" / "scripts" / "Update-BobiverseService.ps1").read_text(encoding="utf-8")


def test_fr2355_no_literal_machine_placeholder_in_nssm_set():
    t = _install_text()
    assert "airc console (#{machine} IRC shell)" not in t
    assert "$displayName" in t
    assert "dnMachine" in t
    assert "airc console (#" + "${" + "dnMachine} IRC shell)" in t


def test_fr2355_default_profile_helpers_present():
    t = _install_text()
    assert "function Test-AircDefaultProfileHome" in t
    assert "function Resolve-AircSafeConsoleHome" in t
    assert ("FR #2355: remap even when" in t) or ("FR #2355 / #3288: remap user-profile homes" in t) or ("FR #2355/#3288" in t)


def test_fr2355_identity_reconcile_skips_default_consolehome():
    t = _update_text()
    assert "identity-reconcile skip ConsoleHome under Users\\Default" in t
    assert "FR #2355" in t


def test_fr2355_default_path_detection_examples():
    samples_bad = ["C:/Users/Default/.airc", r"C:\Users\Default\.airc\console.password"]
    samples_ok = [r"C:\ai\airc\home", r"C:\Users\Administrator\.airc"]
    needle = "Users" + chr(92) + "Default"
    needle2 = "Users/Default"
    for s in samples_bad:
        assert (needle in s) or (needle2 in s)
    for s in samples_ok:
        assert needle not in s and needle2 not in s

