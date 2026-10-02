"""#32: unattended install / tray start must be able to skip the seat-killing tidy."""
from __future__ import annotations

import re
from pathlib import Path

S = Path(__file__).resolve().parent.parent / "scripts"


def _t(name: str) -> str:
    return (S / name).read_text(encoding="utf-8-sig")


def test_start_bobtray_forwards_skiptidy_and_env():
    t = _t("Start-BobTray.ps1")
    assert "[switch]$SkipTidy" in t
    assert "BOBIVERSE_NO_TIDY" in t
    assert re.search(r"Start-BobFleetTray|\$fleetStart[^\n]*-SkipTidy:\$noTidy", t)
    assert "-SkipTidy:$noTidy" in t


def test_install_bob_skips_tidy_for_quiet_and_msi():
    t = _t("Install-Bob.ps1")
    assert "[switch]$SkipTidy" in t
    assert "Test-BobiverseMsiOrQuiet" in t
    # quiet path hands the switch to the interactive launcher
    assert "-RunNow -SkipTidy:$noTidy" in t
    # interactive path appends -SkipTidy to the tray launch args
    assert "$trayLaunch += '-SkipTidy'" in t


def test_interactive_launcher_runs_one_shot_with_skiptidy():
    t = _t("Start-BobTrayInteractive.ps1")
    assert "[switch]$SkipTidy" in t
    assert "-ForceNew -SkipTidy" in t
    # the persistent logon task keeps its normal args (no SkipTidy baked in)
    persistent = [ln for ln in t.splitlines() if ln.lstrip().startswith("$action = New-ScheduledTaskAction")]
    assert persistent and all("SkipTidy" not in ln for ln in persistent)


def test_vendored_fleet_tray_still_supports_skiptidy():
    p = S.parent / "third_party" / "bob-tray" / "tools" / "Start-BobFleetTray.ps1"
    assert "[switch]$SkipTidy" in p.read_text(encoding="utf-8-sig")
