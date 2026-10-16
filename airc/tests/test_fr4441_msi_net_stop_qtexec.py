"""FR #4441: bake proven 1.0.1-hotfix1 stop into Pack (net.exe wait, not sc.exe async).

Walrus hotfix (sha256 4e407648...) proved: QtExec64CmdLine + net stop Airc + MajorUpgrade
afterInstallValidate. FR #4432 landed QtExec64 + afterInstallValidate but left sc.exe
(async); bake net.exe so 1.0.2 matches the proven hotfix.
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
OPS = ROOT / "airc" / "docs" / "airc-ops.md"
TROUBLE = ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-troubleshooting" / "SKILL.md"


def _pack() -> str:
    return PACK.read_text(encoding="utf-8-sig")


def test_fr4441_immediate_stop_uses_net_exe_not_sc():
    text = _pack()
    assert "FR #4441" in text
    assert "net.exe" in text
    assert 'Value="&quot;[System64Folder]net.exe&quot; stop Airc"' in text
    # Proven hotfix: sc stop is async and leaves files locked into costing.
    assert 'Value="&quot;[System64Folder]sc.exe&quot; stop Airc"' not in text
    assert 'Property="QtExec64CmdLine"' in text
    assert "StopAircBeforeValidate" in text


def test_fr4441_keeps_after_install_validate_and_no_deferred_before_rep():
    text = _pack()
    assert "'afterInstallValidate'" in text or '"afterInstallValidate"' in text
    assert 'CustomAction Id="StopAircBeforeUpgrade"' not in text
    assert 'Before="RemoveExistingProducts"' not in text


def test_fr4441_ops_or_skill_documents_net_stop_hotfix():
    ops = OPS.read_text(encoding="utf-8-sig")
    skill = TROUBLE.read_text(encoding="utf-8-sig")
    blob = ops + "\n" + skill
    assert "FR #4441" in blob or "net.exe" in blob or "net stop" in blob
    assert "2613" in blob or "afterInstallValidate" in blob
