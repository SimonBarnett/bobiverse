"""docs/mrb-3557 hostile pins for FR #3513/#3512 fleet-operators + flatten."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
UPDATE = ROOT / "common" / "scripts" / "Update-BobiverseService.ps1"
PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
INSTALL = ROOT / "airc" / "scripts" / "Install-Airc.ps1"
ROSTER = ROOT / "airc" / "config" / "fleet-operators.txt"
SKILL = ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc" / "SKILL.md"


def test_roster_ships_ionos_ear_nick():
    t = ROSTER.read_text(encoding="utf-8")
    assert "bob-win-mpre8vi4u6u" in t
    assert "FR #3513" in t


def test_resolve_and_pack_and_update_wire_roster():
    c = COMMON.read_text(encoding="utf-8-sig")
    assert "function Get-BobiverseAircFleetOperatorRoster" in c
    assert "FR #3513" in c
    assert "Write-Output -NoEnumerate" in c
    p = PACK.read_text(encoding="utf-8-sig")
    assert "fleet-operators.txt" in p
    u = UPDATE.read_text(encoding="utf-8-sig")
    assert "Get-AircSelfUpdateOperatorsProperty" in u
    assert "AIRC_OPERATORS=" in u
    assert "FR #3513" in u


def test_install_flattens_and_passes_installroot_to_resolve():
    t = INSTALL.read_text(encoding="utf-8-sig")
    assert "FR #3512" in t or "flatOps" in t
    chunk = t[t.find("Resolve-BobiverseAircOperatorNicks") :][:1200]
    assert "InstallRoot" in chunk
    assert "FR #3513" in t


def test_skill_cites_3513_roster_and_3512_flatten():
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3513" in skill
    assert "fleet-operators" in skill
    assert "FR #3512" in skill or "flatten" in skill.lower() or "one nick" in skill.lower()
