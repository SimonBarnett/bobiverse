"""FR #6149: company/product fuel-family logos with text fallback."""
from __future__ import annotations

import struct
from pathlib import Path

from repo_layout import ROOT

TRAY = ROOT / "bob" / "tray"
ASSETS = TRAY / "assets" / "fuel-logos"
WATCH = TRAY / "tools" / "Watch-BobTray.ps1"
STATUS = TRAY / "dialogs" / "BobStatus.cs"
COMMON = TRAY / "dialogs" / "BobDialogsCommon.cs"
SYNC = ROOT / "bob" / "scripts" / "Sync-BobTrayFromAgenticBuild.ps1"
MOCKS = ROOT / "bob" / "docs" / "mocks" / "digest-fuel"
FAMILIES = ("cursor", "xai", "opencode", "copilot")


def _png_wh(data: bytes) -> tuple[int, int]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def test_fr6149_four_logo_pngs_exist_and_are_png():
    assert (ASSETS / "LICENSE.md").is_file()
    lic = (ASSETS / "LICENSE.md").read_text(encoding="utf-8")
    assert "original Bobiverse" in lic or "Bobiverse-owned" in lic or "original Bobiverse artwork" in lic
    assert "not official" in lic.lower() or "not official Cursor" in lic
    for name in FAMILIES:
        p = ASSETS / f"{name}.png"
        data = p.read_bytes()
        w, h = _png_wh(data)
        assert w == h and 32 <= w <= 128
        assert len(data) > 100


def test_fr6149_watch_tipform_wires_logo_helpers_and_strip():
    text = WATCH.read_text(encoding="utf-8-sig")
    assert "function Get-BobTrayFuelLogoImage" in text
    assert "function Get-BobTrayFuelLogoFallbackText" in text
    assert "function Add-BobTrayFuelFamilyRow" in text
    assert "FR #6149" in text
    assert "assets\\fuel-logos" in text or "assets\fuel-logos" in text
    # Four families painted
    for fam in ("cursor", "xai", "opencode", "copilot"):
        assert f"Family '{fam}'" in text or f'Family "{fam}"' in text


def test_fr6149_status_draws_logos_with_fallback():
    st = STATUS.read_text(encoding="utf-8")
    cm = COMMON.read_text(encoding="utf-8")
    assert "FuelLogo" in cm and "FuelLogoFallback" in cm
    assert "fuel-logos" in cm
    assert 'Section(g, y, "Cursor Models", "", "cursor")' in st
    # FIX #6180: Copilot uses SelectCopilotLine + titleColor; family logo arg remains.
    assert '"copilot"' in st and "SelectCopilotLine" in st
    assert "FuelLogoFallback" in st


def test_fr6149_mocks_four_logos_and_error_fallback():
    home = (MOCKS / "home.html").read_text(encoding="utf-8")
    err = (MOCKS / "error.html").read_text(encoding="utf-8")
    for fam in FAMILIES:
        assert f'data-family="{fam}"' in home
        assert f"fuel-logos/{fam}.png" in home
        assert f'data-family="{fam}"' in err
    assert "data-logo-fallback" in err
    assert "logo asset missing - text fallback" in err


def test_fr6149_sync_copies_fuel_logos():
    text = SYNC.read_text(encoding="utf-8")
    assert "fuel-logos" in text
    assert "FR #6149" in text


def test_fr6149_no_placeholder_or_scraped_claim():
    for p in (ASSETS / "LICENSE.md", WATCH, SYNC):
        t = p.read_text(encoding="utf-8-sig")
        assert "PLACEHOLDER" not in t.upper()
    # Assets are tiny original badges; refuse obvious scraped multi-MB dumps without license note
    for name in FAMILIES:
        assert (ASSETS / f"{name}.png").stat().st_size < 50_000
