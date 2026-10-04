"""#32: unattended install / tray start must be able to skip the seat-killing tidy."""
from __future__ import annotations

import re
from pathlib import Path
from repo_layout import ROOT  # t773u: split repo; legacy flat paths resolve per service

S = ROOT / "scripts"


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
    # FR #1636: interactive tray launch always includes -SkipTidy (seats kept)
    assert "'-SkipTidy'" in t or '"-SkipTidy"' in t or "-ForceNew', '-SkipTidy'" in t or "-ForceNew -SkipTidy" in t


def test_interactive_launcher_persists_skiptidy_on_logon_task():
    """FR #1636 supersedes #32's 'persistent task without SkipTidy' — ONLOGON must SkipTidy."""
    t = _t("Start-BobTrayInteractive.ps1")
    assert "[switch]$SkipTidy" in t
    assert "trayArgsPersistent" in t
    assert "-SkipTidy" in t
    # Persistent action uses the SkipTidy args variable (or inlines SkipTidy).
    assert "New-ScheduledTaskAction" in t
    assert "trayArgsPersistent" in t or (
        any(
            "New-ScheduledTaskAction" in ln and "SkipTidy" in ln
            for ln in t.splitlines()
        )
    )


def test_vendored_fleet_tray_still_supports_skiptidy():
    p = ROOT / "third_party" / "bob-tray" / "tools" / "Start-BobFleetTray.ps1"
    assert "[switch]$SkipTidy" in p.read_text(encoding="utf-8-sig")
