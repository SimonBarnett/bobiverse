"""FR #4013: non-elevated airc install must not look like a generic 1603/1730.

Unelevated msiexec hit Error 1730 at RemoveExistingProducts. Tip MSI must fail
closed early when not Privileged; Install-Airc.cmd/ps1 self-elevate or exit 740
with a clear message and must not write the FR #3759 fail-reported flag.
"""
from __future__ import annotations

from repo_layout import ROOT

PACK = (ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1").read_text(encoding="utf-8-sig")
COMMON = (ROOT / "common" / "scripts" / "Bobiverse-Common.ps1").read_text(encoding="utf-8-sig")
INSTALL_PS1 = (ROOT / "airc" / "scripts" / "Install-Airc.ps1").read_text(encoding="utf-8-sig")
INSTALL_CMD = (ROOT / "airc" / "scripts" / "Install-Airc.cmd").read_text(encoding="utf-8-sig", errors="replace")
OPS = (ROOT / "airc" / "docs" / "airc-ops.md").read_text(encoding="utf-8-sig")
SKILL = (
    ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-troubleshooting" / "SKILL.md"
).read_text(encoding="utf-8")


def test_fr4013_msi_requires_privileged_early():
    assert "FR #4013" in PACK
    assert "InstallPrivileges" in PACK and "elevated" in PACK
    assert "airc install needs administrator rights" in PACK
    assert "Privileged" in PACK
    idx = PACK.find("FR #4013")
    assert idx > 0
    chunk = PACK[idx : idx + 600]
    assert "Privileged" in chunk
    assert "administrator rights" in chunk


def test_fr4013_uac_relaunch_exits_740_no_throw_on_cancel():
    assert "function Request-BobiverseUacRelaunch" in COMMON
    idx = COMMON.find("function Request-BobiverseUacRelaunch")
    body = COMMON[idx : idx + 1800]
    assert "740" in body
    assert "administrator rights" in body.lower() or "needs administrator" in body.lower()
    assert "FR #4013" in body or "FR#4013" in body
    # Prefer exit 740 over bare throw so PS 4.0 -File does not exit 0
    assert "exit 740" in body.replace(" ", "") or "exit [int]740" in body or 'exit 740' in body


def test_fr4013_install_airc_uses_uac_and_cmd_skips_failflag_on_740():
    assert "Request-BobiverseUacRelaunch" in INSTALL_PS1
    assert "4013" in INSTALL_CMD
    assert "740" in INSTALL_CMD
    assert "administrator rights" in INSTALL_CMD.lower()
    # Must not call outer failure report for elevation-required
    assert "skip" in INSTALL_CMD.lower() and "740" in INSTALL_CMD


def test_fr4013_docs():
    assert "FR #4013" in OPS
    assert "740" in OPS or "administrator" in OPS.lower()
    assert "FR #4013" in SKILL
    assert not (
        ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-troubleshooting" / "SKILL.md"
    ).read_bytes().startswith(b"\xef\xbb\xbf")
