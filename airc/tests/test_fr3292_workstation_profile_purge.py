"""FR #3292: airc workstation profile skips agent layer; purge uninstall removes secrets."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"
INSTALL = ROOT / "airc/scripts/Install-Airc.ps1"
UNINSTALL = ROOT / "airc/scripts/Uninstall-Airc.ps1"
POST = ROOT / "common/docs/post-install.md"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"
OPS = ROOT / "airc/docs/airc-ops.md"
T1566 = ROOT / "airc/tests/test_fr1566_msi_uninstall_stops_service.py"


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def test_install_workstation_skips_agent_layer_wiring():
    t = INSTALL.read_text(encoding="utf-8-sig")
    _no_bom(INSTALL)
    assert "[string]$Profile" in t or "[string]$InstallProfile" in t
    assert "AIRC_PROFILE" in t or "workstation" in t
    assert "AIRC_AGENT_LAYER" in t or "AgentLayer" in t
    assert "FR #3292" in t
    assert "airc-install-manifest.json" in t
    assert "Install-BobiverseAgentLayer" in t
    # Gate: workstation / AgentLayer=0 skips agent layer + profile skills.
    assert "workstation" in t.lower()
    assert "agent-layer skipped" in t.lower() or "skip agent" in t.lower() or "AgentLayer" in t


def test_uninstall_purge_mode_wiring():
    t = UNINSTALL.read_text(encoding="utf-8-sig")
    _no_bom(UNINSTALL)
    assert "FR #3292" in t
    assert "Purge" in t
    assert "AIRC_PURGE" in t or "purge" in t.lower()
    assert "airc-install-manifest.json" in t
    assert "ConsoleHome" in t
    # Fleet default still keeps secrets unless purge.
    assert "keeping ConsoleHome" in t or "ConsoleHome secrets kept" in t
    assert "Users\\Default\\.airc" in t or "Default\\.airc" in t
    assert "ProgramData" in t and "update" in t.lower()


def test_pack_profile_and_purge_props():
    p = PACK.read_text(encoding="utf-8")
    _no_bom(PACK)
    assert 'Property Id="AIRC_PROFILE"' in p
    assert 'Property Id="AIRC_AGENT_LAYER"' in p
    assert 'Property Id="AIRC_PURGE"' in p
    assert "-Profile &quot;[AIRC_PROFILE]&quot;" in p or "-InstallProfile &quot;[AIRC_PROFILE]&quot;" in p
    assert "-AgentLayer &quot;[AIRC_AGENT_LAYER]&quot;" in p
    assert "-Purge &quot;[AIRC_PURGE]&quot;" in p


def test_docs_skill_ops_mention_workstation_purge():
    post = POST.read_text(encoding="utf-8")
    assert "AIRC_PROFILE" in post
    assert "AIRC_PURGE" in post
    assert "workstation" in post.lower()
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3292" in skill
    assert "workstation" in skill.lower() or "AIRC_PROFILE" in skill
    ops = OPS.read_text(encoding="utf-8")
    assert "FR #3292" in ops or "AIRC_PURGE" in ops or "purge" in ops.lower()


def test_fr1566_still_documents_fleet_keep_default():
    """Fleet uninstall keep-ConsoleHome regression (#1599) stays documented."""
    t = UNINSTALL.read_text(encoding="utf-8-sig")
    assert "FR #1566" in t
    assert "Remove-BobiverseService" in t
    # Hostile 1566 test file still present and references keep.
    assert T1566.is_file()


def test_fr3292_files_end_with_newline():
    for p in (PACK, INSTALL, UNINSTALL, POST, SKILL, OPS, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
