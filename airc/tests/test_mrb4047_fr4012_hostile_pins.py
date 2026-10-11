"""Hostile pins for MRB #4047 / FR #4012 (additive after product merge)."""
from __future__ import annotations

from repo_layout import ROOT

COMMON = (ROOT / "common" / "scripts" / "Bobiverse-Common.ps1").read_text(encoding="utf-8-sig")
INSTALL_CMD = (ROOT / "airc" / "scripts" / "Install-Airc.cmd").read_text(encoding="utf-8-sig", errors="replace")


def _serialized_body() -> str:
    idx = COMMON.find("function Invoke-BobiverseMsiexecSerialized")
    assert idx >= 0
    return COMMON[idx : idx + 3200]


def test_mrb4047_refuse_clear_when_live_msiexec_contiguous():
    assert "not clearing InProgress" in COMMON
    assert "still live msiexec after wait" in COMMON
    assert "WaitLiveSec" in COMMON


def test_mrb4047_after_1705_bounce_and_retry_order():
    body = _serialized_body()
    assert "Clear-BobiverseMsiPendingTransaction" in body
    pre = body.find("Clear-BobiverseMsiPendingTransaction -Why 'pre-msiexec'")
    retry = body.find("code -eq 1705")
    after = body.find("Clear-BobiverseMsiPendingTransaction -Why 'after-1705'")
    assert 0 <= pre < retry < after
    assert "restarted msiserver after 1705" in COMMON or "after 1705 (no InProgress key)" in COMMON


def test_mrb4047_install_cmd_clears_before_ps1():
    assert "4012" in INSTALL_CMD
    clear_i = INSTALL_CMD.lower().find("clear-bobiversemsipendingtransaction")
    # Real invoke is -File ...Install-Airc.ps1 (REM comments mention the name earlier)
    file_i = INSTALL_CMD.lower().find('-file "%here%install-airc.ps1"')
    if file_i < 0:
        file_i = INSTALL_CMD.lower().find("-file \"%here%install-airc.ps1\"")
    if file_i < 0:
        file_i = INSTALL_CMD.lower().rfind("install-airc.ps1")
    assert 0 <= clear_i < file_i