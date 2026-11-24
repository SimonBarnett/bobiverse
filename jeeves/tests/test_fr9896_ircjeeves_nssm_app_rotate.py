# -*- coding: utf-8 -*-
"""FR #9896: Install-Jeeves / Update pin NSSM AppRotate* for ircJeeves stdout.log."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
INSTALL = ROOT / "jeeves" / "scripts" / "Install-Jeeves.ps1"
UPDATE = ROOT / "common" / "scripts" / "Update-BobiverseService.ps1"
EVIDENCE = ROOT / "jeeves" / "docs" / "evidence" / "fr8781-walrus-logs-2026-11-24.md"


def test_fr9896_common_defines_approtate_helper():
    t = COMMON.read_text(encoding="utf-8")
    assert "function Set-BobiverseNssmAppRotate" in t
    assert "AppRotateFiles" in t
    assert "AppRotateBytes" in t
    assert "AppRotateOnline" in t
    assert "1048576" in t
    assert "FR #9896" in t
    assert "\u2014" not in t


def test_fr9896_install_jeeves_calls_approtate_helper():
    t = INSTALL.read_text(encoding="utf-8")
    assert "Set-BobiverseNssmAppRotate" in t
    assert "FR #9896" in t
    stdout_i = t.index("AppStdout")
    rotate_i = t.index("Set-BobiverseNssmAppRotate")
    assert rotate_i > stdout_i


def test_fr9896_update_reasserts_approtate_for_jeeves():
    t = UPDATE.read_text(encoding="utf-8")
    assert "Set-BobiverseNssmAppRotate" in t
    assert "post-upgrade-approtate" in t
    assert "jeeves" in t.lower()


def test_fr9896_evidence_notes_missing_rotate():
    """Walrus probe that filed this FR remains as the fail-when class."""
    assert EVIDENCE.is_file()
    t = EVIDENCE.read_text(encoding="utf-8")
    assert "AppRotate" in t
    assert "stdout.log" in t
