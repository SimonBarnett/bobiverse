"""v0.1.20: ear --host explicit (Start-Bob / Install-Bob) and the #70 ergo.exe hard-link bounce (pack + installer)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import ROOT  # t773u: split repo; legacy flat paths resolve per service
S = ROOT / "scripts"


def _t(name: str) -> str:
    return (S / name).read_text("utf-8-sig")


def test_start_bob_passes_host_explicitly_and_validates_it():
    t = _t("Start-Bob.ps1")
    assert "[string]$IrcHost = ''" in t
    assert "--nick $nick --home $BobHome --channel $channel --host $IrcHost" in t
    assert "$env:BOB_IRC_HOST" in t and "'irc.ntsa.uk'" in t
    assert "invalid -IrcHost" in t


def test_install_bob_bakes_the_host_into_the_service_command_line():
    t = _t("Install-Bob.ps1")
    assert "[string]$IrcHost = ''" in t
    assert '-InstallRoot `"$InstallRoot`" -IrcHost $IrcHost"' in t


def test_pack_marks_ergo_exe_permanent_never_overwrite_with_stable_guid():
    t = _t("Pack-BobiverseRelease.ps1")
    assert "-Name -eq 'jeeves'" in t.replace("$", "-") or "$Name -eq 'jeeves'" in t
    i = t.index("ergo\\ergo.exe component not found")
    block = t[i - 400:i + 900]
    assert "Permanent" in block and "NeverOverwrite" in block and "bobiverse-$Name-ergo-component" in block


def test_installer_repairs_a_hardlinked_ergo_without_stopping_it():
    j = _t("Install-Jeeves.ps1")
    assert "Repair-BobiverseErgoHardlink -ErgoExe (Join-Path $ErgoRoot 'ergo.exe')" in j
    c = _t("Bobiverse-Common.ps1")
    assert "function Repair-BobiverseErgoHardlink" in c and "Stop-Service" not in c.split("function Repair-BobiverseErgoHardlink")[1]


@pytest.mark.skipif(sys.platform != "win32" or not shutil.which("powershell"), reason="needs Windows PowerShell + fsutil")
def test_repair_breaks_the_hardlink_and_keeps_the_running_name_usable(tmp_path):
    payload = tmp_path / "jeeves-ergo.exe"
    live = tmp_path / "ergo.exe"
    payload.write_bytes(b"MZ-fake-ergo-binary" * 1000)
    os.link(payload, live)
    script = tmp_path / "t.ps1"
    script.write_text(
        f". '{S / 'Bobiverse-Common.ps1'}'\n"
        f"$n0 = Get-BobiverseHardlinkCount -Path '{live}'\n"
        f"$r = Repair-BobiverseErgoHardlink -ErgoExe '{live}'\n"
        f"$n1 = Get-BobiverseHardlinkCount -Path '{live}'\n"
        f"$r2 = Repair-BobiverseErgoHardlink -ErgoExe '{live}'\n"
        f"Write-Output \"RESULT n0=$n0 repaired=$r n1=$n1 again=$r2\"\n",
        encoding="utf-8-sig",
    )
    out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                         capture_output=True, text=True, timeout=120).stdout
    assert "RESULT n0=2 repaired=True n1=1 again=False" in out, out
    assert live.read_bytes() == payload.read_bytes()
    live.write_bytes(b"rewritten")                       # the MSI rewriting its payload no longer touches Ergo's file
    assert payload.read_bytes().startswith(b"MZ-fake")
