"""FR #6323: fr6149 PLACEHOLDER gate must not trip on timeout/fuel prose comments."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

TRAY = ROOT / "bob" / "tray"
WATCH = TRAY / "tools" / "Watch-BobTray.ps1"
SYNC = ROOT / "bob" / "scripts" / "Sync-BobTrayFromAgenticBuild.ps1"
LICENSE = TRAY / "assets" / "fuel-logos" / "LICENSE.md"
TEST = ROOT / "bob" / "tests" / "test_fr6149_fuel_logos.py"


def test_fr6323_fr6149_gate_is_logo_scoped_not_blanket_watch():
    """The gate forbids logo/asset PLACEHOLDER claims; Watch is logo-scoped only."""
    src = TEST.read_text(encoding="utf-8")
    fn = src[src.index("def test_fr6149_no_placeholder_or_scraped_claim") :]
    rest = fn[1:]
    cut = rest.find("\ndef ")
    fn = fn if cut < 0 else fn[: cut + 1]
    assert "FR #6323" in fn
    assert "logo" in fn.lower()
    # Must not apply a blanket PLACEHOLDER scan to the whole Watch-BobTray.ps1 body.
    assert 'for p in (ASSETS / "LICENSE.md", WATCH, SYNC)' not in fn
    assert "PLACEHOLDER.PNG" in fn
    assert "<<PLACEHOLDER>>" in fn


def test_fr6323_watch_timeout_stub_prose_without_logo_placeholder_token():
    text = WATCH.read_text(encoding="utf-8-sig")
    # After FR #6323 the timeout/fuel comments avoid the bare PLACEHOLDER token.
    low = text.lower()
    assert "timeout stub" in low
    assert "unknown-fuel stub" in low
    assert "PLACEHOLDER" not in text.upper()


def test_fr6323_logo_assets_and_sync_still_forbid_placeholder_token():
    for p in (LICENSE, SYNC):
        t = p.read_text(encoding="utf-8-sig")
        assert "PLACEHOLDER" not in t.upper()
    # Watch must not claim a logo asset placeholder file / token.
    w = WATCH.read_text(encoding="utf-8-sig").upper()
    assert "PLACEHOLDER.PNG" not in w
    assert "<<PLACEHOLDER>>" not in w
    assert "FUEL-LOGOS/PLACEHOLDER" not in w.replace("\\", "/")
