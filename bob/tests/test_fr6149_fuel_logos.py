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
    # FR #6214: Cursor+xAI share one capacity row (xai logo); OpenCode + Copilot stay distinct.
    for fam in ("xai", "opencode", "copilot"):
        assert f"Family '{fam}'" in text or f'Family "{fam}"' in text
    # FR #6285: TipForm capacity heading is xAI weekly (Cursor not mixed in).
    assert "xAI weekly" in text
    # Logo assets + fallback helpers still cover all four families (including cursor).
    assert "Get-BobTrayFuelLogoFallbackText" in text


def test_fr6149_status_draws_logos_with_fallback():
    st = STATUS.read_text(encoding="utf-8")
    cm = COMMON.read_text(encoding="utf-8")
    assert "FuelLogo" in cm and "FuelLogoFallback" in cm
    assert "fuel-logos" in cm
    # FR #6285: one xAI weekly heading (not two capacity headers; Cursor not mixed in).
    assert 'Section(g, y, "xAI weekly", "", "xai")' in st
    assert 'Section(g, y, "Cursor Models"' not in st
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
    """FR #6149 / FR #6323: forbid logo/asset PLACEHOLDER claims; allow Watch prose.

    LICENSE + Sync must not say PLACEHOLDER. Watch-BobTray may use the word in
    comments about timeout/fuel_state stubs; still forbid logo-asset tokens there.
    """
    for p in (ASSETS / "LICENSE.md", SYNC):
        t = p.read_text(encoding="utf-8-sig")
        assert "PLACEHOLDER" not in t.upper()
    watch = WATCH.read_text(encoding="utf-8-sig").upper()
    # Logo-scoped tokens only (FR #6323): do not blanket-scan Watch for PLACEHOLDER.
    assert "PLACEHOLDER.PNG" not in watch
    assert "<<PLACEHOLDER>>" not in watch
    assert "FUEL-LOGOS/PLACEHOLDER" not in watch.replace("\\", "/")
    assert "FUEL-LOGOS\\PLACEHOLDER" not in watch
    # Assets are tiny original badges; refuse obvious scraped multi-MB dumps without license note
    for name in FAMILIES:
        assert (ASSETS / f"{name}.png").stat().st_size < 50_000
