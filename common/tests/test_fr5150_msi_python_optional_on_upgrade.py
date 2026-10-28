"""FR #5150: MSI upgrade must not 1603 when python is missing but bob-ear.exe is present."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
INSTALL_BOB = ROOT / "bob/scripts/Install-Bob.ps1"
INSTALL_JEEVES = ROOT / "jeeves/scripts/Install-Jeeves.ps1"
PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"
FLEET = ROOT / "common/.grok/skills/bobiverse-fleet-ops/SKILL.md"


def test_fr5150_resolve_python_allow_missing():
    text = COMMON.read_text(encoding="utf-8")
    assert "function Resolve-BobiversePython" in text
    assert "[switch]$AllowMissing" in text
    assert "throw 'python.exe not found (run Install-BootstrapTools.ps1)'" in text
    assert "if ($AllowMissing)" in text


def test_fr5150_install_bob_skips_python_when_ear_present():
    text = INSTALL_BOB.read_text(encoding="utf-8")
    assert "Resolve-BobiversePython -AllowMissing" in text
    assert "bob-ear.exe" in text
    assert "FR #5150" in text
    assert "Install-BobiversePythonDeps -Python $Python" in text
    # Must not hard-require python before the ear-exe gate.
    assert "if (-not $Python) { $Python = Resolve-BobiversePython }" not in text


def test_fr5150_install_jeeves_skips_python_when_exe_present():
    text = INSTALL_JEEVES.read_text(encoding="utf-8")
    assert "Resolve-BobiversePython -AllowMissing" in text
    assert "jeeves.exe" in text
    assert "FR #5150" in text


def test_fr5150_pack_bob_jeeves_privileged_launch_condition():
    text = PACK.read_text(encoding="utf-8")
    assert "bob install needs administrator rights" in text
    assert "jeeves install needs administrator rights" in text
    assert text.count("Installed OR Privileged") >= 3


def test_fr5150_fleet_ops_row():
    text = FLEET.read_text(encoding="utf-8")
    assert "5150" in text
    assert "python.exe not found" in text
    assert "bob-ear.exe" in text
