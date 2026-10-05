"""FR #2511: ionos airc re-pack evidence receipt gates."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

EVIDENCE = (
    ROOT
    / "airc"
    / "docs"
    / "evidence"
    / "fr2511-ionos-airc-repack-install-smoke-2026-10-05.md"
)
INSTALL = ROOT / "airc" / "scripts" / "Install-AircConsole.ps1"


def test_fr2511_evidence_records_assert_and_smoke():
    text = EVIDENCE.read_text(encoding="utf-8")
    assert "FR #2511" in text
    assert "Assert-BobiverseReleaseAssets" in text
    assert "selftest ok" in text or "selftest" in text.lower()
    assert "7f0786102935ec48f4b759ccab74fcbf4badeb35e41cab587da0a47ada73e2ad" in text
    assert "result=current" in text
    assert "HomePath" in text


def test_fr2511_tip_install_script_keeps_homepath_fix():
    text = INSTALL.read_text(encoding="utf-8")
    assert "FR #2499" in text
    assert "[string]$HomePath" in text
    assert "automatic $Home is read-only" in text
