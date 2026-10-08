"""MRB #3302 hostile pins: Protect-BobiverseSecretPath SYSTEM+Administrators-only."""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COMMON = REPO / "common" / "scripts" / "Bobiverse-Common.ps1"
INSTALL_CONSOLE = REPO / "airc" / "scripts" / "Install-AircConsole.ps1"
INSTALL_AIRC = REPO / "airc" / "scripts" / "Install-Airc.ps1"
SKILL = REPO / "airc" / ".grok" / "skills" / "bobiverse-airc" / "SKILL.md"


def test_mrb3302_protect_helper_in_common():
    text = COMMON.read_text(encoding="utf-8")
    assert "function Protect-BobiverseSecretPath" in text
    assert "SetAccessRuleProtection" in text
    assert "S-1-5-18" in text and "S-1-5-32-544" in text


def test_mrb3302_installers_call_protect():
    console = INSTALL_CONSOLE.read_text(encoding="utf-8")
    airc = INSTALL_AIRC.read_text(encoding="utf-8")
    assert "Protect-BobiverseSecretPath" in console
    assert "Protect-BobiverseSecretPath" in airc
    assert 'icacls $Path /grant ("{0}:(R)" -f $env:USERNAME)' not in console
    assert "Remove-AircDefaultProfileSecrets" in console
    assert "FR #3288 install\\home" in console


def test_mrb3302_skill_documents_secret_acls():
    text = SKILL.read_text(encoding="utf-8")
    assert "Protect-BobiverseSecretPath" in text
    assert "FR #3288" in text
    assert "SYSTEM" in text and "Administrators" in text
