"""FR #4012: crashed msiexec must not leave a pending transaction that causes Error 1705.

After PsExec/session-0 crash (companion FR #4011 / exit 1601), the next install hit
Error 1705 (previous installation in progress). Clear InProgress / recover msiserver
before msiexec and retry 1705 like 1618.
"""
from __future__ import annotations

from repo_layout import ROOT

COMMON = (ROOT / "common" / "scripts" / "Bobiverse-Common.ps1").read_text(encoding="utf-8-sig")
UPD = (ROOT / "common" / "scripts" / "Update-BobiverseService.ps1").read_text(encoding="utf-8-sig")
INSTALL_CMD = (ROOT / "airc" / "scripts" / "Install-Airc.cmd").read_text(encoding="utf-8-sig", errors="replace")
OPS = (ROOT / "airc" / "docs" / "airc-ops.md").read_text(encoding="utf-8-sig")
SKILL = (
    ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-troubleshooting" / "SKILL.md"
).read_text(encoding="utf-8")


def test_fr4012_common_defines_pending_clear():
    assert "function Clear-BobiverseMsiPendingTransaction" in COMMON
    assert "function Test-BobiverseMsiPendingTransaction" in COMMON
    assert "FR #4012" in COMMON or "FR#4012" in COMMON
    assert "InProgress" in COMMON
    assert "1705" in COMMON


def test_fr4012_serialized_msiexec_retries_1705():
    assert "function Invoke-BobiverseMsiexecSerialized" in COMMON
    # 1705 retry path alongside 1618
    assert "1705" in COMMON
    idx = COMMON.find("function Invoke-BobiverseMsiexecSerialized")
    body = COMMON[idx : idx + 2500]
    assert "1705" in body
    assert "Clear-BobiverseMsiPendingTransaction" in body


def test_fr4012_install_airc_cmd_clears_pending():
    assert "4012" in INSTALL_CMD
    assert "Clear-BobiverseMsiPendingTransaction" in INSTALL_CMD or "pending" in INSTALL_CMD.lower()


def test_fr4012_ops_and_troubleshooting_document_1705():
    assert "FR #4012" in OPS
    assert "1705" in OPS
    assert "FR #4012" in SKILL
    assert "1705" in SKILL
    assert not (ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-troubleshooting" / "SKILL.md").read_bytes().startswith(b"\xef\xbb\xbf")


def test_fr4012_update_path_mentions_pending_or_uses_serialized():
    assert ("Invoke-BobiverseMsiexecSerialized" in UPD) and ("4012" in UPD or "1705" in COMMON)
