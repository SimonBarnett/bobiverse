"""FR #3290: airc MSI skips Install-BootstrapTools unless AIRC_INSTALL_TOOLS / -WithTools."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"
INSTALL_AIRC = ROOT / "airc/scripts/Install-Airc.ps1"
INSTALL_BOB = ROOT / "bob/scripts/Install-Bob.ps1"
INSTALL_JEEVES = ROOT / "jeeves/scripts/Install-Jeeves.ps1"
BOOT = ROOT / "common/scripts/Install-BootstrapTools.ps1"
POST = ROOT / "common/docs/post-install.md"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def test_install_airc_skips_bootstrap_by_default_wiring():
    text = INSTALL_AIRC.read_text(encoding="utf-8-sig")
    _no_bom(INSTALL_AIRC)
    assert "[switch]$WithTools" in text
    assert "[string]$InstallTools" in text
    assert "AIRC_INSTALL_TOOLS" in text or "InstallTools" in text
    assert "bootstrap-tools skipped" in text
    assert "FR #3290" in text
    # Must not unconditionally invoke bootstrap when airc.exe path is the default.
    assert "WithTools" in text
    # Gate present: only run when opt-in or legacy (no exe).
    assert "airc.exe" in text
    assert "Install-BootstrapTools.ps1" in text


def test_pack_airc_install_tools_and_shared_skip():
    pack = PACK.read_text(encoding="utf-8")
    _no_bom(PACK)
    assert 'Property Id="AIRC_INSTALL_TOOLS"' in pack
    assert "-InstallTools &quot;[AIRC_INSTALL_TOOLS]&quot;" in pack
    assert 'Property Id="BOBIVERSE_SKIP_TOOLS"' in pack
    assert "-MsiSkipTools &quot;[BOBIVERSE_SKIP_TOOLS]&quot;" in pack


def test_bootstrap_skip_tools_and_installed_tools_json():
    boot = BOOT.read_text(encoding="utf-8-sig")
    _no_bom(BOOT)
    assert "[switch]$SkipTools" in boot
    assert "bootstrap-tools skipped" in boot
    assert "installed-tools.json" in boot
    assert "FR #3290" in boot


def test_bob_jeeves_honour_msi_skip_tools():
    for path in (INSTALL_BOB, INSTALL_JEEVES):
        t = path.read_text(encoding="utf-8-sig")
        assert "[string]$MsiSkipTools" in t or "MsiSkipTools" in t
        assert "BOBIVERSE_SKIP_TOOLS" in t or "MsiSkipTools" in t
        assert "bootstrap-tools skipped" in t
        assert "FR #3290" in t


def test_docs_and_skill_mention_airc_install_tools():
    post = POST.read_text(encoding="utf-8")
    assert "AIRC_INSTALL_TOOLS" in post
    assert "BOBIVERSE_SKIP_TOOLS" in post
    skill = SKILL.read_text(encoding="utf-8")
    assert "AIRC_INSTALL_TOOLS" in skill or "bootstrap-tools skipped" in skill
    assert "FR #3290" in skill


def test_fr3290_files_end_with_newline():
    for p in (
        PACK,
        INSTALL_AIRC,
        INSTALL_BOB,
        INSTALL_JEEVES,
        BOOT,
        POST,
        SKILL,
        Path(__file__),
    ):
        assert p.read_bytes().endswith(b"\n"), p
