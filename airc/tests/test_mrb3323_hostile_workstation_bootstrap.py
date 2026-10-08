"""MRB #3323 hostile: keep-both FR #3290/#3292 with FR #3291 crash-report props."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"
INSTALL = ROOT / "airc/scripts/Install-Airc.ps1"
UNINSTALL = ROOT / "airc/scripts/Uninstall-Airc.ps1"
INSTALL_BOB = ROOT / "bob/scripts/Install-Bob.ps1"
INSTALL_JEEVES = ROOT / "jeeves/scripts/Install-Jeeves.ps1"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"


def test_mrb3323_pack_keeps_bootstrap_profile_and_crash_report():
    """CONFLICTING keep-both: #3290/#3292 MSI props must coexist with #3291 crash-report."""
    p = PACK.read_text(encoding="utf-8")
    assert 'Property Id="AIRC_INSTALL_TOOLS"' in p
    assert 'Property Id="AIRC_PROFILE"' in p
    assert 'Property Id="AIRC_AGENT_LAYER"' in p
    assert 'Property Id="AIRC_PURGE"' in p
    assert 'Property Id="BOBIVERSE_SKIP_TOOLS"' in p
    assert 'Property Id="BOBIVERSE_CRASH_REPORT"' in p
    assert "-InstallTools &quot;[AIRC_INSTALL_TOOLS]&quot;" in p
    assert "-Profile &quot;[AIRC_PROFILE]&quot;" in p
    assert "-AgentLayer &quot;[AIRC_AGENT_LAYER]&quot;" in p
    assert "-CrashReport &quot;[BOBIVERSE_CRASH_REPORT]&quot;" in p
    assert "-MsiSkipTools &quot;[BOBIVERSE_SKIP_TOOLS]&quot;" in p


def test_mrb3323_install_airc_keeps_all_param_gates():
    t = INSTALL.read_text(encoding="utf-8-sig")
    assert "[string]$InstallTools" in t
    assert "[string]$Profile" in t
    assert "[string]$AgentLayer" in t
    assert "[string]$CrashReport" in t
    assert "bootstrap-tools skipped" in t
    assert "agent-layer skipped" in t.lower() or "AgentLayer" in t
    assert "crash-report.json" in t
    assert "airc-install-manifest.json" in t


def test_mrb3323_bob_jeeves_keep_skip_tools_and_crash_report():
    for path in (INSTALL_BOB, INSTALL_JEEVES):
        t = path.read_text(encoding="utf-8-sig")
        assert "[string]$MsiSkipTools" in t
        assert "[string]$CrashReport" in t
        assert "BOBIVERSE_SKIP_TOOLS" in t
        assert "crash-report.json" in t


def test_mrb3323_fleet_keep_consolehome_unless_purge():
    t = UNINSTALL.read_text(encoding="utf-8-sig")
    assert "FR #1566" in t
    assert "FR #3292" in t
    # Fleet path must still keep ConsoleHome when not purging.
    assert "keeping ConsoleHome" in t or "ConsoleHome secrets kept" in t
    assert "AIRC_PURGE" in t or "[string]$Purge" in t
    # Workstation / purge removes Default home + update state.
    assert "Default\\.airc" in t or "Users\\Default\\.airc" in t


def test_mrb3323_skill_documents_both_frs():
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3290" in skill
    assert "FR #3292" in skill
    assert "AIRC_INSTALL_TOOLS" in skill or "bootstrap-tools skipped" in skill
    assert "AIRC_PROFILE" in skill or "workstation" in skill.lower()
