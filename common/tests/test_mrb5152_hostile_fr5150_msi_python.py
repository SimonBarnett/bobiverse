"""MRB #5152 hostile pins for FR #5150: MSI upgrade without python."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
INSTALL_BOB = ROOT / "bob/scripts/Install-Bob.ps1"
INSTALL_JEEVES = ROOT / "jeeves/scripts/Install-Jeeves.ps1"
PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"
FLEET = ROOT / "common/.grok/skills/bobiverse-fleet-ops/SKILL.md"


def test_mrb5152_allow_missing_returns_null_before_throw():
    text = COMMON.read_text(encoding="utf-8")
    # Order: AllowMissing return must precede the throw.
    i_allow = text.index("if ($AllowMissing) { return $null }")
    i_throw = text.index("throw 'python.exe not found (run Install-BootstrapTools.ps1)'")
    assert i_allow < i_throw


def test_mrb5152_bob_throws_when_python_and_ear_both_missing():
    text = INSTALL_BOB.read_text(encoding="utf-8")
    assert "scripts\\bob-ear.exe" in text or "scripts\\bob-ear.exe" in text.replace("/", "\\")
    assert "throw 'python.exe not found (run Install-BootstrapTools.ps1)'" in text
    assert "WARN FR #5150 python missing; bob-ear.exe present" in text


def test_mrb5152_jeeves_skips_oper_when_python_missing():
    text = INSTALL_JEEVES.read_text(encoding="utf-8")
    assert "WARN FR #5150 skip oper provisioning (python missing)" in text
    assert "jeeves\\jeeves.exe" in text or "jeeves/jeeves.exe" in text
    # else branch still runs provision when python present
    assert "chair_oper.py" in text
    assert "& $Python @opArgs" in text


def test_mrb5152_pack_bob_and_jeeves_each_have_privileged_condition():
    text = PACK.read_text(encoding="utf-8")
    assert 'Message="bob install needs administrator rights"' in text
    assert 'Message="jeeves install needs administrator rights"' in text
    # airc already had Privileged; bob+jeeves add two more → >= 3
    assert text.count("Installed OR Privileged") >= 3
    assert "FR #4013 / #5150" in text or "FR #5150" in text


def test_mrb5152_fleet_ops_pins_1603_and_1730():
    text = FLEET.read_text(encoding="utf-8")
    assert "FR #5150" in text
    assert "1603" in text
    assert "1730" in text
    assert "AllowMissing" in text or "-AllowMissing" in text
