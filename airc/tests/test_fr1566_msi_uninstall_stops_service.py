"""FR #1566: airc MSI uninstall stops/removes Airc service; keeps ConsoleHome secrets."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from repo_layout import ROOT

PACK = ROOT / "scripts" / "Pack-BobiverseRelease.ps1"
UNINSTALL_PS1 = ROOT / "scripts" / "Uninstall-Airc.ps1"
UNINSTALL_CMD = ROOT / "scripts" / "Uninstall-Airc.cmd"
OPS = ROOT / "docs" / "airc-ops.md"
COMMON = ROOT / "scripts" / "Bobiverse-Common.ps1"


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_uninstall_airc_script_exists_and_tears_down_service_only():
    assert UNINSTALL_PS1.is_file(), "Uninstall-Airc.ps1 missing"
    assert UNINSTALL_CMD.is_file(), "Uninstall-Airc.cmd missing"
    t = _txt(UNINSTALL_PS1)
    assert "Remove-BobiverseService" in t
    assert "Airc" in t
    assert "Resolve-BobiverseNssm" in t
    # Fleet default keeps ConsoleHome (#1599). FR #3292 purge is gated (doPurge / AIRC_PURGE).
    assert "FR #1566" in t or "FR 1566" in t
    assert "ConsoleHome" in t  # documented keep
    assert "keeping ConsoleHome" in t or "ConsoleHome secrets kept" in t
    assert "doPurge" in t
    assert "AIRC_PURGE" in t
    assert "if ($doPurge)" in t


def test_uninstall_cmd_launches_ps1():
    c = _txt(UNINSTALL_CMD)
    assert "Uninstall-Airc.ps1" in c
    assert "powershell" in c.lower()


def test_pack_wires_airc_rununinstall_before_removefiles():
    p = _txt(PACK)
    assert "SetUninstallCmd" in p
    assert "RunUninstall" in p
    assert "Uninstall-Airc.cmd" in p
    assert 'REMOVE="ALL"' in p
    assert "NOT UPGRADINGPRODUCTCODE" in p
    assert "Before=\"RemoveFiles\"" in p or "Before='RemoveFiles'" in p
    # airc-only: uninstall CA gated on product name
    assert "$Name -eq 'airc'" in p or "eq 'airc'" in p
    assert "CAQuietExec64" in p
    assert 'Return="ignore"' in p or "Return='ignore'" in p
    # Must schedule uninstall CA before RemoveFiles while scripts still on disk
    idx_set = p.index("SetUninstallCmd")
    idx_run = p.index("RunUninstall")
    assert idx_set < idx_run or "SetUninstallCmd" in p[p.index("InstallExecuteSequence") :]


def test_ops_doc_documents_uninstall_keeps_consolehome():
    t = _txt(OPS)
    assert "FR #1566" in t
    assert "Uninstall-Airc" in t
    assert "ConsoleHome" in t
    assert "Remove-BobiverseService" in t or "stop/remove" in t.lower() or "stops/removes" in t.lower()


def test_common_still_exposes_remove_bobiverse_service():
    t = _txt(COMMON)
    assert "function Remove-BobiverseService" in t
