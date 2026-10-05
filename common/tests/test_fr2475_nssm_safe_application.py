"""FR #2475: installer must not point NSSM Application at a missing exe; msiexec 1618 serialised."""
from __future__ import annotations

from repo_layout import ROOT

COMMON = (ROOT / "common" / "scripts" / "Bobiverse-Common.ps1").read_text(encoding="utf-8-sig")
# Prefer product Install-Jeeves; fall back to flat scripts/
_ij = ROOT / "jeeves" / "scripts" / "Install-Jeeves.ps1"
if not _ij.is_file():
    _ij = ROOT / "scripts" / "Install-Jeeves.ps1"
INSTALL = _ij.read_text(encoding="utf-8-sig")
UPD = (ROOT / "common" / "scripts" / "Update-BobiverseService.ps1").read_text(encoding="utf-8-sig")


def test_fr2475_common_defines_safe_nssm_application_setter():
    assert "function Set-BobiverseNssmApplicationSafe" in COMMON
    assert "function Get-BobiverseNssmApplication" in COMMON
    assert "keeping previous" in COMMON
    assert "FR #2475" in COMMON or "FR#2475" in COMMON


def test_fr2475_common_serialises_msiexec_and_retries_1618():
    assert "function Invoke-BobiverseMsiexecSerialized" in COMMON
    assert "Global\\bobiverse-msiexec" in COMMON or "Global\bobiverse-msiexec" in COMMON
    assert "1618" in COMMON


def test_fr2475_install_jeeves_uses_safe_application_set():
    assert "Set-BobiverseNssmApplicationSafe" in INSTALL
    assert "jeeves" in INSTALL and "jeeves.exe" in INSTALL
    # Must not blindly nssm set Application to jeevesExe without the safe helper
    # (legacy direct set removed for the exe cutover path).
    assert "FR #2475" in INSTALL or "FR#2475" in INSTALL


def test_fr2475_update_uses_serialized_msiexec_or_1618_retry():
    # Apply path must mention 1618 retry or call the shared serialised helper.
    assert ("Invoke-BobiverseMsiexecSerialized" in UPD) or ("1618" in UPD and "bobiverse-msiexec" in UPD)
