"""FR #70: MSI RunInstall must forward public properties (OPERFILE/SKIPERGO/MACHINEID/...).

Also locks the already-shipped nssm/ergo Permanent+NeverOverwrite wiring that stops BobIrcd
bounces on jeeves MSI upgrade.
"""
from __future__ import annotations

from repo_layout import ROOT

S = ROOT / "scripts"


def _t(name: str) -> str:
    return (S / name).read_text(encoding="utf-8-sig")


def test_pack_declares_public_msi_properties_and_forwards_them_to_runinstall():
    p = _t("Pack-BobiverseRelease.ps1")
    assert "$installArgs = switch ($Name)" in p
    assert "$msiProps = switch ($Name)" in p
    assert 'Property Id="OPERFILE"' in p
    assert 'Property Id="SKIPERGO"' in p
    assert 'Property Id="MACHINEID"' in p
    assert 'Property Id="SKIPCOPY"' in p
    assert 'Property Id="IRCHOST"' in p
    # SetInstallCmd must still forward $installArgs (not a hard-coded -InstallRoot-only line).
    # FR #3685 wraps with cmd.exe /d /c call so .cmd exit codes reach CAQuietExec (FR #3715).
    assert "cmd.exe /d /c call" in p
    assert '[INSTALLDIR]scripts\\$installCmd&quot;$installArgs"' in p
    assert 'Id="SetInstallCmd"' in p
    assert "-OperFile &quot;[OPERFILE]&quot;" in p
    assert "-MsiSkipErgo &quot;[SKIPERGO]&quot;" in p
    assert "-MachineId &quot;[MACHINEID]&quot;" in p
    # FR #2564 / MRB #2566: ProductVersion must reach Install-*.ps1 for VERSION assert
    assert "-MsiProductVersion &quot;[ProductVersion]&quot;" in p
    assert "#70: RunInstall forwards" in p or "#70: public MSI properties" in p
    # FR #3291: crash-report opt-out MSI property
    assert 'Property Id="BOBIVERSE_CRASH_REPORT"' in p
    assert "-CrashReport &quot;[BOBIVERSE_CRASH_REPORT]&quot;" in p


def test_install_jeeves_maps_msi_skip_strings_to_switches():
    t = _t("Install-Jeeves.ps1")
    assert "[string]$MsiSkipErgo = ''" in t
    assert "[string]$MsiSkipCopy = ''" in t
    assert "if ($MsiSkipErgo -eq '1') { $SkipErgo = $true }" in t
    assert "if ($MsiSkipCopy -eq '1') { $SkipCopy = $true }" in t


def test_install_bob_maps_msi_skipcopy_string():
    t = _t("Install-Bob.ps1")
    assert "[string]$MsiSkipCopy = ''" in t
    assert "if ($MsiSkipCopy -eq '1') { $SkipCopy = $true }" in t


def test_pack_keeps_nssm_and_jeeves_ergo_permanent_neveroverwrite():
    p = _t("Pack-BobiverseRelease.ps1")
    assert "bobiverse-$Name-nssm-component" in p
    assert "bobiverse-$Name-ergo-component" in p
    assert "SetAttribute('Permanent', 'yes')" in p
    assert "SetAttribute('NeverOverwrite', 'yes')" in p


def test_watch_bobircd_is_ascii_or_bom_and_has_no_smart_dash():
    raw = (S / "Watch-BobIrcd.ps1").read_bytes()
    text = raw.decode("utf-8-sig")
    assert "attempting Start-Service" in text
    assert "\u2014" not in text  # em-dash broke WinPS 5.1 parse without BOM historically
    non_ascii = any(b > 127 for b in raw)
    assert (not non_ascii) or raw.startswith(b"\xef\xbb\xbf")
